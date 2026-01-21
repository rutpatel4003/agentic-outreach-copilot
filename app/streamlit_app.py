import streamlit as st
import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import pandas as pd
from urllib.parse import urlparse, urljoin

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.workflows.outreach_graph import OutreachWorkflow, WorkflowStatus
from src.agents.tracking_agent import TrackingAgent
from src.agents.reply_agent import ReplyAgent
from src.database.models import MessageChannel, OutreachStatus
from src.utils.prompt_templates import MessageType, MessageTone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Cold Outreach Copilot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)


def init_session_state():
    if 'workflow' not in st.session_state:
        st.session_state.workflow = OutreachWorkflow()
    if 'tracker' not in st.session_state:
        st.session_state.tracker = TrackingAgent()
    if 'reply_agent' not in st.session_state:
        st.session_state.reply_agent = ReplyAgent()
    if 'workflow_results' not in st.session_state:
        st.session_state.workflow_results = []
    if 'current_result' not in st.session_state:
        st.session_state.current_result = None
    if 'company_groups' not in st.session_state:
        st.session_state.company_groups = []  # List of {name, url, manual_urls: {about, careers, news, team}}


def render_sidebar():
    with st.sidebar:
        st.title("⚙️ Configuration")

        st.subheader("📄 Resume")
        resume_file = st.file_uploader(
            "Upload Resume",
            type=['pdf', 'docx', 'txt'],
            help="Upload your resume in PDF, DOCX, or TXT format"
        )
        
        resume_path = None
        if resume_file is not None:
            upload_dir = Path("data/uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)
            resume_path = upload_dir / resume_file.name
            resume_path.write_bytes(resume_file.read())
            st.success(f"✅ {resume_file.name}")

        st.subheader("🎯 Job Settings")
        target_role = st.text_input(
            "Target Role",
            value="Software Engineer",
            help="The job title you're targeting"
        )
        
        message_type = st.selectbox(
            "Message Type",
            options=["LinkedIn Connection", "LinkedIn Message", "Email"],
            index=1
        )
        
        tone = st.selectbox(
            "Tone",
            options=["Professional", "Casual", "Enthusiastic"],
            index=0
        )
        
        st.subheader("🛡️ Guardrails")
        skip_guardrails = st.checkbox(
            "Skip Guardrails (faster)",
            value=False,
            help="Skip fact-checking and tone validation"
        )
        
        max_retries = st.slider(
            "Max Retries",
            min_value=1,
            max_value=5,
            value=2,
            help="Retry generation if guardrails fail"
        )

        st.subheader(" Scraper Settings")

        js_rendering = st.checkbox(
            "Enable JS Rendering",
            value=True,
            help="Wait for JavaScript to load (slower but better for modern sites like OpenAI, Google)"
        )

        if js_rendering:
            scroll_page = st.checkbox(
                "Scroll Page",
                value=True,
                help="Scroll down to trigger lazy-loaded content (job listings)"
            )

            js_wait_time = st.slider(
                "JS Wait Time (seconds)",
                min_value=1,
                max_value=10,
                value=3,
                help="How long to wait for JavaScript to render content"
            )
        else:
            scroll_page = False
            js_wait_time = 0

        return {
            'resume_path': str(resume_path) if resume_path else None,
            'target_role': target_role,
            'message_type': message_type.lower().replace(' ', '_'),
            'tone': tone.lower(),
            'skip_guardrails': skip_guardrails,
            'max_retries': max_retries,
            'js_rendering': js_rendering,
            'scroll_page': scroll_page,
            'js_wait_time': js_wait_time * 1000  # convert to milliseconds
        }


def render_generate_tab(config: Dict):
    st.header("🚀 Generate Outreach")

    # input method tabs
    input_tab1, input_tab2, input_tab3 = st.tabs(["📝 Quick Entry", "📁 CSV Upload", "📦 Company Groups"])

    companies_to_process = []  # list of {url, manual_urls, contact_name, contact_email}

    with input_tab1:
        st.subheader("Quick Entry")
        col1, col2 = st.columns([2, 1])

        with col1:
            company_input = st.text_area(
                "Company URLs (one per line)",
                height=100,
                placeholder="https://nuro.ai\nhttps://openai.com",
                help="Enter company URLs for auto-discovery",
                key="quick_company_urls"
            )

            # manual URL Overrides 
            with st.expander("⚙️ Manual Page URLs (Optional)", expanded=False):
                st.caption("💡 **Tip:** Comma-separate multiple URLs. First URL is used for the first company, etc.")

                col_a, col_b = st.columns(2)
                with col_a:
                    manual_careers = st.text_input(
                        "Careers URLs",
                        placeholder="https://nuro.ai/careers, https://openai.com/careers",
                        help="Comma-separated careers page URLs",
                        key="quick_manual_careers"
                    )
                    manual_news = st.text_input(
                        "News URLs",
                        placeholder="https://nuro.ai/blog, https://openai.com/news",
                        help="Comma-separated news page URLs",
                        key="quick_manual_news"
                    )
                with col_b:
                    manual_about = st.text_input(
                        "About URLs",
                        placeholder="https://nuro.ai/company, https://openai.com/about",
                        help="Comma-separated about page URLs",
                        key="quick_manual_about"
                    )
                    manual_team = st.text_input(
                        "Team URLs",
                        placeholder="https://nuro.ai/team, https://openai.com/team",
                        help="Comma-separated team page URLs",
                        key="quick_manual_team"
                    )

            contact_col1, contact_col2 = st.columns(2)
            with contact_col1:
                contact_name = st.text_input("Contact Name (optional)", key="quick_contact_name")
            with contact_col2:
                contact_email = st.text_input("Contact Email (optional)", key="quick_contact_email")

        with col2:
            js_status = f"On ({config.get('js_wait_time', 3000)//1000}s)" if config.get('js_rendering', True) else "Off"
            st.info(f"""
            **Configuration:**
            - Role: {config['target_role']}
            - Type: {config['message_type']}
            - Tone: {config['tone']}
            - Guardrails: {'Off' if config['skip_guardrails'] else 'On'}
            - JS Rendering: {js_status}
            """)

    with input_tab2:
        st.subheader("CSV Upload")
        st.caption("Upload a CSV with columns: `company_name`, `company_url`, `target_role` (optional), `manual_about`, `manual_careers`, `manual_news`, `manual_team`")

        csv_file = st.file_uploader("Upload CSV", type=['csv'], key="csv_upload")

        if csv_file:
            try:
                df = pd.read_csv(csv_file)
                st.success(f"✅ Loaded {len(df)} companies")
                st.dataframe(df.head(10), use_container_width=True)

                # store parsed companies
                if 'csv_companies' not in st.session_state:
                    st.session_state.csv_companies = []

                st.session_state.csv_companies = []
                for _, row in df.iterrows():
                    manual_urls = {}
                    if pd.notna(row.get('manual_about', '')):
                        manual_urls['about'] = str(row['manual_about']).strip()
                    if pd.notna(row.get('manual_careers', '')):
                        manual_urls['careers'] = str(row['manual_careers']).strip()
                    if pd.notna(row.get('manual_news', '')):
                        manual_urls['news'] = str(row['manual_news']).strip()
                    if pd.notna(row.get('manual_team', '')):
                        manual_urls['team'] = str(row['manual_team']).strip()

                    st.session_state.csv_companies.append({
                        'url': row['company_url'],
                        'name': row.get('company_name', ''),
                        'target_role': row.get('target_role', config['target_role']),
                        'manual_urls': manual_urls if manual_urls else None
                    })

            except Exception as e:
                st.error(f"❌ Failed to parse CSV: {e}")

        # download sample CSV
        sample_csv_path = Path("data/sample_companies.csv")
        if sample_csv_path.exists():
            st.download_button(
                "📥 Download Sample CSV",
                data=sample_csv_path.read_text(),
                file_name="sample_companies.csv",
                mime="text/csv"
            )
        else:
            st.caption("Sample CSV not found. Create `data/sample_companies.csv`")

    with input_tab3:
        st.subheader("Company Groups")
        st.caption("Create named groups with custom manual URLs for each company.")

        # add new group form
        with st.expander("➕ Add New Company Group", expanded=True):
            group_name = st.text_input("Group Name", placeholder="Nuro - Software Engineer", key="new_group_name")
            group_url = st.text_input("Company URL", placeholder="https://nuro.ai", key="new_group_url")

            gcol1, gcol2 = st.columns(2)
            with gcol1:
                group_careers = st.text_input("Careers URL", key="new_group_careers")
                group_news = st.text_input("News URL", key="new_group_news")
            with gcol2:
                group_about = st.text_input("About URL", key="new_group_about")
                group_team = st.text_input("Team URL", key="new_group_team")

            if st.button("➕ Add Group", key="add_group_btn"):
                if group_url:
                    manual_urls = {}
                    if group_careers:
                        manual_urls['careers'] = group_careers
                    if group_about:
                        manual_urls['about'] = group_about
                    if group_news:
                        manual_urls['news'] = group_news
                    if group_team:
                        manual_urls['team'] = group_team

                    st.session_state.company_groups.append({
                        'name': group_name or group_url,
                        'url': group_url,
                        'manual_urls': manual_urls if manual_urls else None
                    })
                    st.success(f"✅ Added: {group_name or group_url}")
                    st.rerun()
                else:
                    st.error("❌ Company URL is required")

        # show existing groups
        if st.session_state.company_groups:
            st.markdown("**📦 Saved Groups:**")
            for idx, group in enumerate(st.session_state.company_groups):
                col_g1, col_g2 = st.columns([4, 1])
                with col_g1:
                    manual_count = len(group.get('manual_urls', {}) or {})
                    st.markdown(f"**{idx+1}. {group['name']}** - {group['url']} ({manual_count} manual URLs)")
                with col_g2:
                    if st.button("🗑️", key=f"delete_group_{idx}"):
                        st.session_state.company_groups.pop(idx)
                        st.rerun()

            if st.button("🗑️ Clear All Groups", key="clear_groups"):
                st.session_state.company_groups = []
                st.rerun()
        else:
            st.info("No groups added yet. Create your first group above!")
    
    # generate button (outside tabs, always visible)
    st.divider()

    if st.button("🚀 Generate Messages", type="primary", use_container_width=True):
        if not config['resume_path']:
            st.error("❌ Please upload a resume first")
            return

        companies_to_process = []

        # 1. check Quick Entry tab
        quick_companies = [url.strip() for url in company_input.split('\n') if url.strip()]

        if quick_companies:
            # parse comma-separated manual URLs
            careers_list = [u.strip() for u in manual_careers.split(',') if u.strip()] if manual_careers else []
            about_list = [u.strip() for u in manual_about.split(',') if u.strip()] if manual_about else []
            news_list = [u.strip() for u in manual_news.split(',') if u.strip()] if manual_news else []
            team_list = [u.strip() for u in manual_team.split(',') if u.strip()] if manual_team else []

            for idx, url in enumerate(quick_companies):
                manual_urls = {}
                if idx < len(careers_list):
                    manual_urls['careers'] = careers_list[idx]
                if idx < len(about_list):
                    manual_urls['about'] = about_list[idx]
                if idx < len(news_list):
                    manual_urls['news'] = news_list[idx]
                if idx < len(team_list):
                    manual_urls['team'] = team_list[idx]

                companies_to_process.append({
                    'url': url,
                    'manual_urls': manual_urls if manual_urls else None,
                    'contact_name': contact_name if contact_name else None,
                    'contact_email': contact_email if contact_email else None,
                    'target_role': config['target_role']
                })

        # 2. check CSV Upload
        if hasattr(st.session_state, 'csv_companies') and st.session_state.csv_companies:
            for company in st.session_state.csv_companies:
                companies_to_process.append({
                    'url': company['url'],
                    'manual_urls': company.get('manual_urls'),
                    'contact_name': None,
                    'contact_email': None,
                    'target_role': company.get('target_role', config['target_role'])
                })

        # 3. check Company Groups
        if st.session_state.company_groups:
            for group in st.session_state.company_groups:
                companies_to_process.append({
                    'url': group['url'],
                    'manual_urls': group.get('manual_urls'),
                    'contact_name': None,
                    'contact_email': None,
                    'target_role': config['target_role']
                })

        # validation
        if not companies_to_process:
            st.error("❌ Please enter at least one company URL (Quick Entry, CSV, or Groups)")
            return

        # de-duplicate by URL
        seen_urls = set()
        unique_companies = []
        for company in companies_to_process:
            if company['url'] not in seen_urls:
                seen_urls.add(company['url'])
                unique_companies.append(company)
        companies_to_process = unique_companies

        st.info(f"📋 Processing {len(companies_to_process)} companies...")
        
        st.session_state.workflow_results = []
        overall_progress_bar = st.progress(0)
        overall_status = st.empty()

        # create containers for each company's progress
        company_progress_containers = {}
        for idx, company in enumerate(companies_to_process):
            with st.container():
                st.markdown(f"**{idx+1}. {company['url']}**")
                company_progress_containers[company['url']] = {
                    'progress_bar': st.progress(0),
                    'status_text': st.empty()
                }

        st.divider()

        for i, company in enumerate(companies_to_process):
            company_url = company['url']
            overall_status.markdown(f"**Processing {i+1}/{len(companies_to_process)}**: {company_url}")

            # get this company's progress container
            container = company_progress_containers[company_url]

            # define progress callback for this company
            def progress_callback(step: str, progress: float, status: str):
                container['progress_bar'].progress(progress)
                container['status_text'].text(status)

            # update workflow with progress callback
            st.session_state.workflow.progress_callback = progress_callback

            try:
                result = st.session_state.workflow.run(
                    resume_path=config['resume_path'],
                    target_role=company.get('target_role', config['target_role']),
                    company_url=company_url,
                    message_type=config['message_type'],
                    tone=config['tone'],
                    contact_name=company.get('contact_name'),
                    contact_email=company.get('contact_email'),
                    skip_guardrails=config['skip_guardrails'],
                    max_retries=config['max_retries'],
                    manual_urls=company.get('manual_urls'),
                    js_rendering=config.get('js_rendering', True),
                    scroll_page=config.get('scroll_page', True),
                    js_wait_time=config.get('js_wait_time', 3000)
                )

                st.session_state.workflow_results.append(result)
                container['status_text'].text("✅ Complete!")

            except Exception as e:
                logger.error(f"Failed to process {company_url}: {e}")
                container['status_text'].text(f"❌ Failed: {str(e)}")

            overall_progress_bar.progress((i + 1) / len(companies_to_process))

        overall_status.markdown("**✅ All companies processed!**")
        st.success(f"Generated messages for {len(st.session_state.workflow_results)} companies")

        # clear CSV companies after processing (optional: keep groups)
        if hasattr(st.session_state, 'csv_companies'):
            st.session_state.csv_companies = []

        st.rerun()
    
    if st.session_state.workflow_results:
        st.divider()
        render_results()


def render_extracted_contacts(scraped_data: Dict, result_index: int = 0):
    """Display extracted contacts from scraped data"""
    contacts = scraped_data.get('extracted_contacts', [])

    if not contacts:
        st.warning("⚠️ No contacts automatically extracted. Try finding contacts manually:")
        st.info("""
        **💡 How to find contacts:**
        1. Search company name + role on **LinkedIn**
        2. Use tools like Hunter.io or RocketReach for email finding
        3. Check the Team/Leadership page for names
        """)
        return None

    st.success(f"📇 Found {len(contacts)} potential contacts!")

    # create a dataframe for display
    contact_data = []
    for c in contacts:
        relevance = c.get('relevance_score', 0)
        relevance_label = "🔥 High" if relevance >= 0.7 else ("⭐ Medium" if relevance >= 0.5 else "○ Low")

        contact_data.append({
            'Name': c.get('name', 'Unknown'),
            'Title': c.get('title', '-'),
            'Email': c.get('email', '-'),
            'LinkedIn': '🔗' if c.get('linkedin_url') else '-',
            'Source': c.get('source_page', 'team').title(),
            'Relevance': relevance_label
        })

    df = pd.DataFrame(contact_data)
    st.dataframe(df, width='stretch', hide_index=True)

    # let user select a contact
    contact_names = [f"{c.get('name', 'Unknown')} - {c.get('title', 'No title')}" for c in contacts]
    selected_idx = st.selectbox(
        "Select a contact to use:",
        range(len(contact_names)),
        format_func=lambda i: contact_names[i],
        key=f"contact_select_{result_index}"
    )

    if selected_idx is not None:
        selected_contact = contacts[selected_idx]
        col1, col2 = st.columns(2)
        with col1:
            st.text_input(
                "Selected Contact Name",
                value=selected_contact.get('name', ''),
                key=f"selected_name_{result_index}",
                disabled=True
            )
        with col2:
            email = selected_contact.get('email', '')
            linkedin = selected_contact.get('linkedin_url', '')
            contact_info = email if email else (linkedin if linkedin else 'Not found')
            st.text_input(
                "Contact Info",
                value=contact_info,
                key=f"selected_info_{result_index}",
                disabled=True
            )

        if selected_contact.get('linkedin_url'):
            st.markdown(f"🔗 [View LinkedIn Profile]({selected_contact['linkedin_url']})")

        return selected_contact

    return None

def render_extracted_jobs(scraped_data: Dict, target_role: str = ""):
    """Display extracted job listings"""
    jobs = scraped_data.get('extracted_jobs', [])

    if not jobs:
        st.warning("⚠️ No job listings extracted. The careers page might use JavaScript rendering.")
        st.info("💡 **Tip:** Use the manual URL option to provide the exact careers search URL")
        return

    base_url = (
        scraped_data.get("company_url")
        or (scraped_data.get("pages", {}).get("careers", {}) or {}).get("url", "")
    )

    def make_url(job_url: str) -> str:
        if not job_url:
            return ""
        if job_url.startswith("http"):
            return job_url
        return urljoin(base_url + "/", job_url)

    # filter for matching jobs if target role provided
    if target_role:
        matching = [j for j in jobs if j.get('match_score', 0) > 0.3]
        other = [j for j in jobs if j.get('match_score', 0) <= 0.3]

        if matching:
            st.success(f"🎯 Found {len(matching)} jobs matching '{target_role}':")
            for job in matching[:5]:
                score = job.get('match_score', 0)
                match_indicator = "🔥" if score > 0.7 else "⭐"
                job_url = make_url(job.get('url', ''))
                if job_url:
                    st.markdown(f"{match_indicator} **[{job['title']}]({job_url})** 🔗")
                else:
                    st.markdown(f"{match_indicator} **{job['title']}**")

        if other:
            with st.expander(f"Other {len(other)} jobs found"):
                for job in other[:10]:
                    job_url = make_url(job.get('url', ''))
                    if job_url:
                        st.markdown(f"• [{job['title']}]({job_url}) 🔗")
                    else:
                        st.markdown(f"• {job['title']}")
    else:
        st.write(f"**{len(jobs)} job titles found:**")
        for job in jobs[:10]:
            job_url = make_url(job.get('url', ''))
            if job_url:
                st.markdown(f"• [{job['title']}]({job_url}) 🔗")
            else:
                st.markdown(f"• {job['title']}")


def render_scraped_data_summary(scraped_data: Dict):
    """Display summary of scraped company data"""
    pages = scraped_data.get('pages', {})
    metadata = scraped_data.get('metadata', {})

    st.write(f"**Company:** {scraped_data.get('company_name', 'Unknown')}")
    st.write(f"**Success Rate:** {metadata.get('success_rate', 'N/A')} ({metadata.get('successful_pages', 0)}/{metadata.get('total_pages_attempted', 0)} pages)")

    if pages:
        st.write("**Pages Found:**")
        for page_type, page_data in pages.items():
            if isinstance(page_data, dict):
                url = page_data.get('url', 'N/A')
                text_length = page_data.get('text_length', 0)
                status = "✅" if text_length > 200 else "⚠️"

                st.markdown(f"{status} **{page_type.title()}**: [{url}]({url})")
                st.caption(f"   Content length: {text_length} chars")

                # Show preview of content
                text_preview = page_data.get('text', '')[:300]
                if text_preview:
                    with st.expander(f"Preview {page_type} content"):
                        st.text(text_preview + "...")
    else:
        st.warning("No pages were successfully scraped")


def render_results():
    st.subheader("📊 Results")

    for i, result in enumerate(st.session_state.workflow_results):
        with st.expander(
            f"{'✅' if result['status'] == WorkflowStatus.TRACKED.value else '❌'} "
            f"{result.get('company_name', 'Unknown')} - {result['status']}",
            expanded=(i == 0)
        ):
            if result.get('error'):
                st.error(f"Error: {result['error']}")

                # show what was scraped even on error
                scraped_data = result.get('scraped_data', {})
                if scraped_data:
                    # show extracted contacts even on error
                    contacts = scraped_data.get('extracted_contacts', [])
                    if contacts:
                        with st.expander("📇 Extracted Contacts (still useful!)", expanded=True):
                            render_extracted_contacts(scraped_data, result_index=i)

                    with st.expander("🔍 View Scraped Data"):
                        render_scraped_data_summary(scraped_data)
                continue

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Status", result['status'])
            with col2:
                variants = result.get('message_variants', [])
                st.metric("Variants", len(variants))
            with col3:
                guardrail = result.get('guardrail_result', {})
                score = guardrail.get('overall_score', 0)
                st.metric("Quality", f"{score:.0%}")

            # show extracted contacts prominently
            scraped_data = result.get('scraped_data', {})
            contacts = scraped_data.get('extracted_contacts', [])

            if contacts:
                st.subheader("📇 Who to Contact")
                with st.expander("View Extracted Contacts", expanded=True):
                    render_extracted_contacts(scraped_data, result_index=i)
            else:
                st.info("👤 **Who to send this to?** No contacts were auto-extracted. Check the scraped data below or find contacts on LinkedIn.")

            # show extracted jobs
            jobs = scraped_data.get('extracted_jobs', [])
            if jobs:
                with st.expander(f"💼 Job Listings Found ({len(jobs)})", expanded=False):
                    target_role = result.get('target_role', '')
                    render_extracted_jobs(scraped_data, target_role)

            # show scraped data summary
            if scraped_data:
                with st.expander("🔍 View Scraped Data (Pages Found)", expanded=False):
                    render_scraped_data_summary(scraped_data)
            
            # show all message variants
            variants = result.get('message_variants', [])
            if variants:
                import re

                st.markdown("**Generated Messages:**")

                # variant selector if multiple variants exist
                if len(variants) > 1:
                    variant_labels = [f"Variant {idx+1} ({v['word_count']} words)" for idx, v in enumerate(variants)]
                    selected_variant_idx = st.selectbox(
                        "Choose a variant:",
                        range(len(variants)),
                        format_func=lambda idx: variant_labels[idx],
                        key=f"variant_select_{i}"
                    )
                else:
                    selected_variant_idx = 0

                variant = variants[selected_variant_idx]

                show_raw = st.checkbox(
                    "Show raw message (with citations)",
                    value=False,
                    key=f"show_raw_{i}"
                )

                if show_raw:
                    display_message = variant['message']
                else:
                    clean_message = re.sub(r'\[source:\s*[^\]]+\]', '', variant['message'])
                    clean_message = re.sub(r'\s+', ' ', clean_message).strip()
                    display_message = clean_message

                # use variant index and company URL in key to ensure uniqueness across generations
                company_url = result.get('company_url', '').replace('https://', '').replace('http://', '').replace('/', '_')
                st.text_area(
                    "Message",
                    value=display_message,
                    height=200,
                    key=f"msg_{company_url}_{i}_v{selected_variant_idx}",
                    label_visibility="collapsed"
                )

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.caption(f"📝 {variant['word_count']} words")
                with col2:
                    st.caption(f"📌 {len(variant['citations'])} citations")
                with col3:
                    st.caption(f"💡 {len(variant['skills_highlighted'])} skills")

                if variant['citations']:
                    with st.expander("View Citations"):
                        for citation in variant['citations']:
                            st.markdown(f"- {citation}")
            
            if result.get('guardrail_result'):
                with st.expander("Guardrails Report"):
                    gr = result['guardrail_result']
                    st.write(f"**Status:** {gr['status']}")
                    st.write(f"**Score:** {gr['overall_score']:.2%}")
                    st.write(f"**Checks Passed:** {gr['passed_checks']}/{gr['total_checks']}")
                    
                    if gr.get('feedback'):
                        st.write("**Feedback:**")
                        for feedback in gr['feedback']:
                            st.markdown(f"- {feedback}")


def render_tracking_tab():
    st.header("📊 CRM Dashboard")
    
    tracker = st.session_state.tracker
    
    col1, col2, col3, col4 = st.columns(4)
    
    stats = tracker.get_outreach_stats()
    
    with col1:
        st.metric("Total Sent", stats.total_sent)
    with col2:
        st.metric("Replied", stats.total_replied, delta=f"{stats.reply_rate:.1f}%")
    with col3:
        st.metric("No Response", stats.total_no_response)
    with col4:
        st.metric("Pending Follow-ups", stats.pending_followups)
    
    if stats.avg_response_time_hours:
        st.info(f"📈 Average Response Time: {stats.avg_response_time_hours:.1f} hours")
    
    st.divider()
    
    tab1, tab2, tab3 = st.tabs(["All Messages", "Pending Follow-ups", "Analytics"])
    
    with tab1:
        messages = tracker.get_all_messages(limit=100)
        
        if messages:
            data = []
            for msg in messages:
                data.append({
                    'ID': msg.id,
                    'Company': msg.company.name,
                    'Role': msg.target_role,
                    'Channel': msg.channel.value,
                    'Status': msg.status.value,
                    'Sent': msg.sent_at.strftime('%Y-%m-%d') if msg.sent_at else 'N/A',
                    'Response Time (hrs)': f"{msg.response_time_hours:.1f}" if msg.response_time_hours else 'N/A'
                })
            
            df = pd.DataFrame(data)
            st.dataframe(df, width='stretch', hide_index=True)
            
            st.subheader("Update Status")
            col1, col2, col3 = st.columns(3)
            with col1:
                msg_id = st.number_input("Message ID", min_value=1, step=1)
            with col2:
                new_status = st.selectbox(
                    "New Status",
                    options=[s.value for s in OutreachStatus]
                )
            with col3:
                st.write("")
                st.write("")
                if st.button("Update"):
                    success = tracker.update_message_status(
                        msg_id,
                        OutreachStatus[new_status.upper()]
                    )
                    if success:
                        st.success("✅ Status updated")
                        st.rerun()
                    else:
                        st.error("❌ Update failed")
        else:
            st.info("No messages tracked yet. Generate some outreach first!")
    
    with tab2:
        followups = tracker.get_pending_followups(days_ahead=30)
        
        if followups:
            for followup in followups:
                msg = followup.original_message
                with st.expander(
                    f"📅 {followup.scheduled_date.strftime('%Y-%m-%d')} - "
                    f"{msg.company.name} (Follow-up #{followup.followup_number})"
                ):
                    st.write(f"**Company:** {msg.company.name}")
                    st.write(f"**Role:** {msg.target_role}")
                    sent_at_str = msg.sent_at.strftime('%Y-%m-%d') if msg.sent_at else "N/A"
                    st.write(f"**Original Sent:** {sent_at_str}")
                    st.write(f"**Message Preview:**")
                    st.text(msg.message_content[:200] + "...")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        notes = st.text_input("Notes", key=f"notes_{followup.id}")
                    with col2:
                        schedule_next = st.checkbox(
                            "Schedule next follow-up",
                            value=True,
                            key=f"schedule_{followup.id}"
                        )
                    
                    if st.button("✅ Complete Follow-up", key=f"complete_{followup.id}"):
                        success = tracker.complete_followup(
                            followup.id,
                            notes=notes if notes else None,
                            schedule_next=schedule_next
                        )
                        if success:
                            st.success("Follow-up completed!")
                            st.rerun()
        else:
            st.info("No pending follow-ups in the next 30 days")
    
    with tab3:
        if stats.total_sent > 0:
            chart_data = pd.DataFrame({
                'Status': ['Replied', 'No Response', 'Rejected'],
                'Count': [stats.total_replied, stats.total_no_response, stats.total_rejected]
            })
            st.bar_chart(chart_data.set_index('Status'))
            
            st.write(f"**Reply Rate:** {stats.reply_rate:.1f}%")
            
            if stats.avg_response_time_hours:
                st.write(f"**Avg Response Time:** {stats.avg_response_time_hours:.1f} hours "
                        f"({stats.avg_response_time_hours/24:.1f} days)")
        else:
            st.info("Generate some outreach to see analytics")


def render_reply_tab():
    st.header("💬 Reply Analysis")
    
    tracker = st.session_state.tracker
    reply_agent = st.session_state.reply_agent
    
    messages = tracker.get_all_messages(status=OutreachStatus.SENT, limit=50)
    
    if not messages:
        st.info("No sent messages to analyze. Generate and track outreach first!")
        return
    
    message_options = {
        f"{msg.id} - {msg.company.name} ({msg.target_role})": msg
        for msg in messages
    }
    
    selected_key = st.selectbox(
        "Select Message to Analyze Reply",
        options=list(message_options.keys())
    )
    
    selected_message = message_options[selected_key]
    
    st.text_area(
        "Original Message",
        value=selected_message.message_content,
        height=150,
        disabled=True
    )
    
    reply_text = st.text_area(
        "Received Reply",
        height=200,
        placeholder="Paste the reply you received here..."
    )
    
    if st.button("🔍 Analyze Reply", type="primary"):
        if not reply_text.strip():
            st.error("Please enter a reply to analyze")
            return
        
        with st.spinner("Analyzing reply..."):
            try:
                analysis = reply_agent.analyze_reply(
                    original_message=selected_message.message_content,
                    reply_text=reply_text,
                    candidate_info={
                        'name': 'Candidate',
                        'email': selected_message.contact.email if selected_message.contact else None,
                        'skills': []
                    },
                    generate_suggestions=True,
                    num_suggestions=2
                )
                
                st.session_state.current_result = analysis
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Category", analysis.classification.category.value.title())
                with col2:
                    st.metric("Sentiment", analysis.classification.sentiment.value.title())
                with col3:
                    st.metric("Action", analysis.classification.action_needed.value.title())
                
                st.write(f"**Confidence:** {analysis.classification.confidence:.0%}")
                
                if analysis.classification.key_points:
                    st.write("**Key Points:**")
                    for point in analysis.classification.key_points:
                        st.markdown(f"- {point}")
                
                if analysis.suggestions:
                    st.divider()
                    st.subheader("💡 Suggested Responses")
                    
                    for i, suggestion in enumerate(analysis.suggestions, 1):
                        with st.expander(f"Response Option {i}", expanded=(i == 1)):
                            st.text_area(
                                "Suggested Response",
                                value=suggestion.message,
                                height=150,
                                key=f"suggestion_{i}",
                                label_visibility="collapsed"
                            )
                            st.caption(f"Tone: {suggestion.tone} | Action: {suggestion.suggested_action}")
                
                if st.button("✅ Mark as Replied"):
                    tracker.update_message_status(
                        selected_message.id,
                        OutreachStatus.REPLIED,
                        response_text=reply_text
                    )
                    st.success("Message marked as replied!")
                    st.rerun()
                
            except Exception as e:
                logger.error(f"Reply analysis failed: {e}")
                st.error(f"Analysis failed: {str(e)}")


def main():
    init_session_state()
    
    st.title("🤖 Cold Outreach Copilot")
    st.caption("AI-powered job search automation with built-in guardrails")
    
    config = render_sidebar()
    
    tab1, tab2, tab3 = st.tabs(["🚀 Generate", "📊 Track", "💬 Replies"])
    
    with tab1:
        render_generate_tab(config)
    
    with tab2:
        render_tracking_tab()
    
    with tab3:
        render_reply_tab()
    
    with st.sidebar:
        st.divider()
        st.caption("Built with LangGraph • Ollama • Streamlit")
        st.caption("USC Master's Portfolio Project")


if __name__ == "__main__":
    main()