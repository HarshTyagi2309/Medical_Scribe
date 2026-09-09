"""User-facing MediNote guide, rendered inside the authenticated workspace."""

import streamlit as st


def render_usage_guide():
    """Explain the existing recording, review, correction and history workflow."""
    st.markdown(
        """
        <div class="mn-page-header">
            <div>
                <div class="mn-eyebrow">Getting started</div>
                <div class="mn-title">How to use MediNote</div>
                <div class="mn-subtitle">From your consultation audio to organized
                    clinical notes. Follow these steps to get started.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown("### 1. Open a consultation")
        st.write(
            "Select Consultation in the sidebar. To clear the current workspace "
            "and begin another consultation, select New Consultation."
        )

    with st.container(border=True):
        st.markdown("### 2. Choose how to capture audio")
        handsfree, manual, upload = st.tabs(
            ["🎙️ Hands-Free", "🎤 Manual Record", "📁 Upload Audio"]
        )
        with handsfree:
            st.write(
                'Enable the microphone and allow browser access. Say "start recording" '
                "to begin. Recording stops after 5 seconds of silence, and the app "
                "automatically starts processing the captured consultation."
            )
            st.caption("Speak clearly and keep background noise low.")
        with manual:
            st.write(
                "Use the microphone control in Manual Record to start recording. "
                "Stop when the consultation is complete, then listen to the audio preview. "
                "Select Analyze & Save Consultation to process it."
            )
        with upload:
            st.write(
                "Choose an existing WAV, M4A, OGG or WEBM audio file in Upload Audio. "
                "Check the audio preview, then select Analyze & Save Consultation."
            )

    with st.container(border=True):
        st.markdown("### 3. Review the transcript and clinical summary")
        st.write(
            "After processing, read the Consultation Transcript and Clinical summary. "
            "The summary can include vitals, diagnosis, symptoms, medications, "
            "recommended tests, doctor instructions and follow-up information. "
            "Details not found in the audio may be shown as not recorded or not stated."
        )
        st.info(
            "AI-generated information must be reviewed and verified by an authorized "
            "healthcare professional before clinical use."
        )

    with st.container(border=True):
        st.markdown("### 4. Correct the saved record when needed")
        st.write(
            "Successful processing saves the consultation automatically. Under Doctor "
            "Correction, select Edit Saved Record to update the transcript or clinical "
            "details. Select Save Correction to save your edits, or Cancel to leave "
            "the saved record unchanged."
        )

    with st.container(border=True):
        st.markdown("### 5. Find previous consultations")
        st.write(
            "Open Consultation History from the sidebar. Search by patient name or "
            "patient ID, expand a record and select Open consultation to review it. "
            "Use Refresh to reload the list."
        )

    st.markdown("### Need help?")
    with st.expander("The microphone is not working"):
        st.write(
            "Allow microphone access in your browser and check that the correct "
            "microphone is selected. If Hands-Free is unavailable, try Manual Record "
            "or Upload Audio."
        )
    with st.expander("Analyze & Save Consultation is disabled"):
        st.write("Record or upload audio first. The button becomes available once audio is selected.")
    with st.expander("The backend is unavailable or processing fails"):
        st.write(
            "Check the connection status in the workspace. Ask your administrator "
            "to start the service if it is offline. If processing times out, try again."
        )
    with st.expander("This audio has already been processed"):
        st.write(
            "MediNote detects duplicate audio. It opens the existing record when "
            "available so you can review the consultation already saved."
        )

    if st.button("🩺 Open Consultation", type="primary", key="guide_open_consultation"):
        st.session_state.workspace_view = "consultation"
        st.rerun()
