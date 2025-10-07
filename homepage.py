import streamlit as st
import subprocess
import webbrowser
import os
import time

st.set_page_config(
    page_title="LegalMorph Launcher", 
    page_icon="⚖️",
    layout="centered"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        margin-bottom: 3rem;
    }
    .app-button {
        margin: 1rem 0;
        padding: 1rem;
        border-radius: 10px;
        border: 2px solid #e0e0e0;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-size: 1.2rem;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .app-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
    }
    .description {
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .status-box {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
        text-align: center;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
    }
</style>
""", unsafe_allow_html=True)

# ---- HEADER ----
st.markdown('<div class="main-header">', unsafe_allow_html=True)
st.title("Legal Data Pipeline")
st.subheader("Automated Legal Data Processing System")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="description">', unsafe_allow_html=True)
st.write("Select a stage to launch its dedicated UI in a new browser tab:")
st.markdown('</div>', unsafe_allow_html=True)

# ---- APP PATHS (relative to current directory) ----
apps = {
    "Transformation (Custom → Base → Merge)": "Transformation/main_combined_ui.py", 
    "Deduplication & Unification": "Transformation/deduplication/main_deduplication_ui.py"
}

# Web scraper options
web_scrapers = {
    "EastLaw Scraper": "Extraction/main_run_eastlaw.py",
    "EasyLaw Scraper": "Extraction/main_run_easylaw.py"
}

# ---- PORTS (each app gets its own tab) ----
ports = {
    "Extraction (Web Scraping)": 8502,
    "Transformation (Custom → Base → Merge)": 8503,
    "Deduplication & Unification": 8504,
}

# Individual scraper ports
scraper_ports = {
    "EastLaw Scraper": 8502,
    "EasyLaw Scraper": 8505,  # Different port for EasyLaw
}

# ---- DESCRIPTIONS ----
descriptions = {
    "Extraction (Web Scraping)": "Scrape legal cases and statutes from EastLaw and EasyLaw",
    "Transformation (Custom → Base → Merge)": "Transform raw text into structured JSON format",
    "Deduplication & Unification": "Remove duplicates and unify legal data schemas"
}

def launch_app(path, port, app_name):
    """Launch a Streamlit app on a given port and open in browser."""
    try:
        # Check if file exists
        if not os.path.exists(path):
            st.error(f"❌ App file not found: {path}")
            return False
        
        # Check if port is already in use
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        
        if result == 0:
            st.warning(f"⚠️ Port {port} is already in use. Opening existing app...")
            webbrowser.open_new_tab(f"http://localhost:{port}")
            return True
        
        # Launch the app
        cmd = f"streamlit run \"{path}\" --server.port {port} --server.headless true"
        subprocess.Popen(cmd, shell=True)
        
        # Wait a moment for the app to start
        time.sleep(2)
        
        # Open in browser
        webbrowser.open_new_tab(f"http://localhost:{port}")
        
        st.success(f"✅ {app_name} launched successfully on port {port}")
        return True
        
    except Exception as e:
        st.error(f"❌ Failed to launch {app_name}: {str(e)}")
        return False

def check_port_status(port):
    """Check if a port is currently in use."""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        return result == 0
    except:
        return False

def update_app_status():
    """Update the status of all launched apps by checking their ports."""
    if 'launch_status' in st.session_state:
        for app_name, status in st.session_state.launch_status.items():
            if status:  # If app was previously marked as running
                # Check if it's a scraper app
                if "Extraction" in app_name:
                    # Extract scraper name from app_name (e.g., "Extraction (EastLaw Scraper)")
                    scraper_name = app_name.replace("Extraction (", "").replace(")", "")
                    port = scraper_ports.get(scraper_name)
                else:
                    port = ports.get(app_name)
                
                if port:
                    # Check if port is still active
                    if not check_port_status(port):
                        st.session_state.launch_status[app_name] = False

# Initialize session state for status tracking
if 'launch_status' not in st.session_state:
    st.session_state.launch_status = {}

# Update app status by checking ports
update_app_status()

# ---- WEB SCRAPER SECTION ----
st.markdown("### Web Scraping")
st.write("Select a web scraper to launch:")

# Web scraper selection
selected_scraper = st.selectbox(
    "Choose Web Scraper:",
    list(web_scrapers.keys()),
    help="Select which web scraper to launch"
)

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown(f"""
    <div style="margin-bottom: 0.5rem;">
        <strong>Extraction (Web Scraping)</strong><br>
        <small style="color: #666;">{descriptions['Extraction (Web Scraping)']} - {selected_scraper}</small>
    </div>
    """, unsafe_allow_html=True)

with col2:
    if st.button("Launch Scraper", key="btn_scraper", use_container_width=True):
        # Use the specific port for the selected scraper
        scraper_port = scraper_ports[selected_scraper]
        success = launch_app(web_scrapers[selected_scraper], scraper_port, f"Extraction ({selected_scraper})")
        st.session_state.launch_status[f"Extraction ({selected_scraper})"] = success
        st.rerun()

# ---- OTHER APPLICATIONS ----
st.markdown("### Other Applications")

for label, path in apps.items():
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown(f"""
        <div style="margin-bottom: 0.5rem;">
            <strong>{label}</strong><br>
            <small style="color: #666;">{descriptions[label]}</small>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        if st.button(f"Launch", key=f"btn_{label}", use_container_width=True):
            success = launch_app(path, ports[label], label)
            st.session_state.launch_status[label] = success
            st.rerun()

# ---- STATUS DISPLAY ----
if st.session_state.launch_status:
    st.markdown("### Launch Status")
    
    for app_name, status in st.session_state.launch_status.items():
        if status:
            # Get the correct port for the app
            port = None
            if "Extraction" in app_name:
                # Extract scraper name from app_name
                scraper_name = app_name.replace("Extraction (", "").replace(")", "")
                port = scraper_ports.get(scraper_name)
            else:
                port = ports.get(app_name)
            
            if port:
                st.markdown(f'<div class="status-box success-box">✅ {app_name} - Running on port {port}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="status-box success-box">✅ {app_name} - Running</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="status-box info-box">❌ {app_name} - Not running</div>', unsafe_allow_html=True)

# ---- FOOTER ----
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    <p>💡 <strong>Tip:</strong> Each application runs independently. You can have multiple apps open simultaneously.</p>
    <p>🔧 <strong>Note:</strong> Close browser tabs to stop individual apps. The homepage will automatically detect when apps are closed.</p>
    <p>🔄 <strong>Auto-refresh:</strong> The status updates automatically when you close browser tabs.</p>
</div>
""", unsafe_allow_html=True)
