"""
Streamlit app for SRA Agent with password protection, chat UI, and rate limiting.
"""

import streamlit as st
import hmac
import json
import uuid
from datetime import datetime

from sra_agent import create_sra_agent, query_sra, set_bq_credentials
from rate_limiter import SessionRateLimiter, RateLimitConfig


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


def initialize_session_state():
    """Initialize Streamlit session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())

    if "agent" not in st.session_state:
        st.session_state.agent = None

    if "rate_limiter" not in st.session_state:
        config = RateLimitConfig(
            max_queries_per_session=10,
            max_queries_per_hour=50,
            cooldown_seconds=30
        )
        st.session_state.rate_limiter = SessionRateLimiter(st.session_state, config)

    if "query_results" not in st.session_state:
        st.session_state.query_results = []

    if "credentials_loaded" not in st.session_state:
        st.session_state.credentials_loaded = False

    if "error_count" not in st.session_state:
        st.session_state.error_count = 0


def trim_chat_history(max_messages: int = 20):
    """Trim chat history to prevent memory issues.

    Keeps only the most recent messages, maintaining conversation context.
    """
    if len(st.session_state.messages) > max_messages:
        removed_count = len(st.session_state.messages) - max_messages
        st.session_state.messages = st.session_state.messages[-max_messages:]
        return removed_count
    return 0


def clear_session_on_error():
    """Clear problematic session state to allow recovery."""
    st.session_state.error_count += 1
    if st.session_state.error_count > 2:
        # Reset agent after multiple errors
        st.session_state.agent = None
        st.session_state.error_count = 0


def get_error_recovery_message(error: Exception) -> tuple[str, str]:
    """Generate user-friendly error message with recovery suggestions.

    Returns: (user_message, recovery_suggestion)
    """
    error_str = str(error).lower()

    if "bigquery" in error_str or "database" in error_str:
        return (
            "❌ Database connection error",
            "The SRA database is temporarily unavailable. Please try again in a few moments."
        )
    elif "timeout" in error_str or "deadline" in error_str:
        return (
            "❌ Query timeout",
            "The query took too long to complete. Try a more specific search (e.g., narrow down by organism or platform)."
        )
    elif "authentication" in error_str or "credentials" in error_str:
        return (
            "❌ Authentication error",
            "There's an issue with the database credentials. Please contact the administrator."
        )
    elif "no results" in error_str or "zero" in error_str:
        return (
            "⚠️ No results found",
            "Your query didn't match any records. Try using different keywords or organisms."
        )
    elif "rate limit" in error_str:
        return (
            "❌ Rate limit exceeded",
            "You've exceeded your query limit. Please wait before trying again."
        )
    else:
        return (
            "❌ Unexpected error",
            "An unexpected error occurred. Try refreshing the page or clearing the chat."
        )


def load_gcp_credentials():
    """Load and inject GCP credentials from Streamlit secrets."""
    try:
        if "gcp_service_account" in st.secrets:
            credentials_dict = dict(st.secrets["gcp_service_account"])
            set_bq_credentials(credentials_dict)
            return True
        return False
    except Exception as e:
        st.warning(f"⚠️ Failed to load GCP credentials: {str(e)}")
        return False


def create_agent():
    """Create and cache the SRA agent."""
    if st.session_state.agent is None:
        try:
            st.session_state.agent = create_sra_agent()
        except Exception as e:
            st.error(f"❌ Failed to initialize agent: {str(e)}")
            st.session_state.agent = None
    return st.session_state.agent


def display_sidebar():
    """Display sidebar with rate limiting info and controls."""
    with st.sidebar:
        st.title("📊 Query Status")

        # Rate limiting info
        remaining = st.session_state.rate_limiter.get_remaining_queries()
        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                "Session Limit",
                f"{remaining['remaining_session']}/10"
            )

        with col2:
            st.metric(
                "Hour Limit",
                f"{remaining['remaining_hour']}/50"
            )

        if remaining["cooldown_active"]:
            st.warning(
                f"⏱️ Cooldown active: {remaining['seconds_until_next']:.0f}s remaining"
            )

        st.divider()

        # Clear chat button
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.query_results = []
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.error_count = 0
            st.rerun()

        # Reset agent button (hidden by default)
        if st.session_state.error_count > 0:
            if st.button("🔄 Reset Agent", use_container_width=True, help="Click if agent is unresponsive"):
                st.session_state.agent = None
                st.session_state.error_count = 0
                st.rerun()

        # Download results button
        if st.session_state.query_results:
            download_data = {
                "thread_id": st.session_state.thread_id,
                "timestamp": datetime.now().isoformat(),
                "results": st.session_state.query_results
            }
            st.download_button(
                label="📥 Download Results (JSON)",
                data=json.dumps(download_data, indent=2),
                file_name=f"sra_results_{st.session_state.thread_id[:8]}.json",
                mime="application/json",
                use_container_width=True
            )

        st.divider()
        st.caption("💡 Tip: Ask about genomic data, organisms, sequencing platforms, and more!")


def display_chat_history():
    """Display chat history."""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def handle_user_input():
    """Handle user input and agent response with enhanced error handling."""
    if prompt := st.chat_input("Ask about genomic data..."):
        # Check rate limit before processing
        can_query, reason = st.session_state.rate_limiter.can_query()

        if not can_query:
            st.error(f"❌ {reason}")
            return

        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Trim chat history to prevent memory issues (keep last 20 messages)
        removed = trim_chat_history(max_messages=20)
        if removed > 0:
            st.info(f"💾 Trimmed chat history (removed {removed} old messages to free memory)")

        # Get agent response
        agent = create_agent()
        if agent is None:
            st.error("❌ Agent is not initialized. Please refresh the page.")
            st.session_state.messages.pop()
            return

        with st.spinner("🔄 Querying the SRA database..."):
            progress_placeholder = st.empty()

            try:
                progress_placeholder.info("🔍 Extracting parameters from your query...")

                # Query the agent
                result = query_sra(
                    agent,
                    message=prompt,
                    thread_id=st.session_state.thread_id
                )

                progress_placeholder.info("💾 Processing results...")

                # Record the query for rate limiting
                st.session_state.rate_limiter.record_query()
                st.session_state.error_count = 0  # Reset error count on success

                # Store result for download
                st.session_state.query_results.append({
                    "user_query": prompt,
                    "timestamp": datetime.now().isoformat(),
                    "result": result
                })

                # Add assistant response to chat
                response_text = result.get("response", "No response generated")
                st.session_state.messages.append({"role": "assistant", "content": response_text})

                progress_placeholder.empty()
                st.success("✅ Query completed successfully!")

                # Display additional context if available
                if result.get("results"):
                    with st.expander(f"📊 Query Details ({len(result['results'])} results)"):
                        st.json({
                            "organism": result.get("organism"),
                            "library_source": result.get("library_source"),
                            "platform": result.get("platform"),
                            "keywords": result.get("keywords"),
                            "total_count": result.get("total_count"),
                            "sample_results": result.get("results", [])[:3]
                        })

                st.rerun()

            except Exception as e:
                progress_placeholder.empty()

                # Get user-friendly error message
                error_title, recovery_msg = get_error_recovery_message(e)

                # Display error with recovery suggestion
                st.error(error_title)
                st.info(f"💡 {recovery_msg}")

                # Show technical details in expander for debugging
                with st.expander("📋 Technical Details"):
                    st.code(str(e), language="text")

                # Clear session state on error
                clear_session_on_error()

                # Remove the user message if there was an error
                if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
                    st.session_state.messages.pop()


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

    # Initialize session state
    initialize_session_state()

    # Load GCP credentials on first run
    if not st.session_state.credentials_loaded:
        load_gcp_credentials()
        st.session_state.credentials_loaded = True

    # Display sidebar with rate limiting controls
    display_sidebar()

    # Display chat history
    display_chat_history()

    # Handle user input
    handle_user_input()


if __name__ == "__main__":
    main()
