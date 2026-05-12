import os
import shutil
import tempfile
from typing import Optional, Any

def create_session_dir(session_id: str) -> str:
    """
    Creates a secure temporary directory for the given session.
    The directory is created within the OS's temp folder.
    """
    # Create a unique directory inside the system's temp folder
    prefix = f"autotest_{session_id}_"
    session_dir = tempfile.mkdtemp(prefix=prefix)
    return session_dir

def save_uploaded_file(uploaded_file: Any, session_dir: str) -> Optional[str]:
    """
    Saves an uploaded Streamlit file to the session directory securely.
    """
    if uploaded_file is None:
        return None
    
    file_path = os.path.join(session_dir, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    return file_path

def cleanup_session_dir(session_dir: str) -> None:
    """
    Completely and securely removes the session directory and all its contents.
    Ignores errors to prevent crashes during cleanup.
    """
    if session_dir and os.path.exists(session_dir):
        shutil.rmtree(session_dir, ignore_errors=True)
