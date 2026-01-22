"""
Streamlit app for SRA Agent with password protection.
"""

import streamlit as st
import hmac
import hashlib


def check_password() -> bool:
    """Check if user has entered the correct password."""

    def password_entered():
        """Callback when password is submitted."""
        if hmac.compare_digest(st.session_state["password"], st.secrets.get("app_password", "")):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.text_input(
        "Enter password:",
        type="password",
        key="password",
        on_change=password_entered,
        placeholder="Password"
    )

    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("❌ Incorrect password")

    return False


def main():
    """Main app."""
    st.set_page_config(
        page_title="SRA Agent",
        page_icon="🔬",
        layout="wide"
    )

    st.title("🔬 SRA Agent")
    st.markdown("Query genomic data from the Sequence Read Archive using natural language.")

    if not check_password():
        st.stop()

    # Password correct - initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "thread_id" not in st.session_state:
        import uuid
        st.session_state.thread_id = str(uuid.uuid4())

    if "agent" not in st.session_state:
        st.session_state.agent = None

    st.success("✅ Authenticated")

    st.info(
        "**Demo**: This interface will be connected to the SRA agent in the next milestone. "
        "For now, you can see the basic structure with password protection."
    )


if __name__ == "__main__":
    main()
