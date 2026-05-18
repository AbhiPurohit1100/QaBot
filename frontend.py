import streamlit as st
import requests
import time

# =========================================
# CONFIG
# =========================================

API_URL = "http://127.0.0.1:8000/generate-testcases"

st.set_page_config(
    page_title="AI Testcase Generator",
    page_icon="🧠",
    layout="wide"
)

# =========================================
# CSS
# =========================================

st.markdown("""
<style>

.block-container {
    max-width: 1200px;
    padding-top: 2rem;
    padding-bottom: 2rem;
}

/* textarea */

textarea {
    font-family: monospace !important;
}

/* status cards */

.status-card {
    border-radius: 16px;
    padding: 22px 24px;
    margin-bottom: 18px;
    border: 1px solid;
}

.status-card h3 {
    margin-top: 0;
    margin-bottom: 14px;
}

.status-card ul {
    margin-bottom: 0;
}

.status-pending {
    background-color: #111827;
    border-color: #374151;
    color: #d1d5db;
}

.status-running {
    background-color: #450a0a;
    border-color: #ef4444;
    color: #fecaca;
}

.status-completed {
    background-color: #052e16;
    border-color: #22c55e;
    color: #bbf7d0;
}

/* labels */

.label {
    font-size: 15px;
    font-weight: 700;
    margin-top: 18px;
    margin-bottom: 8px;
}

/* score */

.score-box {
    padding: 28px;
    border-radius: 18px;
    text-align: center;
    background: linear-gradient(
        135deg,
        #111827,
        #1f2937
    );
    border: 1px solid #374151;
    margin-bottom: 30px;
}

.score-number {
    font-size: 64px;
    font-weight: 800;
    margin-bottom: 8px;
    color: white;
}

.score-label {
    font-size: 18px;
    color: #d1d5db;
}

/* pills */

.pass-pill {
    display: inline-block;
    background-color: #052e16;
    color: #22C55E;
    padding: 8px 14px;
    border-radius: 999px;
    font-weight: 700;
    margin-top: 12px;
}

.fail-pill {
    display: inline-block;
    background-color: #450a0a;
    color: #ef4444;
    padding: 8px 14px;
    border-radius: 999px;
    font-weight: 700;
    margin-top: 12px;
}



</style>
""", unsafe_allow_html=True)

# =========================================
# HEADER
# =========================================

st.title("🧠 AI Testcase Generator")

st.caption(
    "LangGraph + Groq + Judge0 powered intelligent testcase validation and code improvement"
)

# =========================================
# DEFAULT CODE
# =========================================

default_code = """import java.util.*;

public class Main {

    public static void main(String[] args) {

        Scanner sc = new Scanner(System.in);

        int a = sc.nextInt();
        int b = sc.nextInt();

        System.out.println(a + b);
    }
}
"""

# =========================================
# INPUT
# =========================================

code = st.text_area(
    "Paste Your Code",
    value=default_code,
    height=350
)

# =========================================
# BUTTON
# =========================================

generate_button = st.button(
    "🚀 Generate, Validate & Improve Code",
    use_container_width=True
)

# =========================================
# STATUS CARD FUNCTION
# =========================================

def render_status_card(
    title,
    points,
    status="pending",
    icon="⏳"
):

    status_class = {
        "pending": "status-pending",
        "running": "status-running",
        "completed": "status-completed"
    }.get(status, "status-pending")

    points_html = ""

    for point in points:

        points_html += f"<li>{point}</li>"

    st.markdown(
        f"""
<div class="status-card {status_class}">
    <h3>{icon} {title}</h3>
    <ul>
        {points_html}
    </ul>
</div>
""",
        unsafe_allow_html=True
    )

# =========================================
# RENDER ALL STATUS CARDS
# =========================================

def render_all_steps(active_step=None, completed_steps=None):

    if completed_steps is None:
        completed_steps = []

    steps = [
        {
            "key": "understanding",
            "title": "Understanding Code",
            "icon": "🧠",
            "points": [
                "Detecting programming language",
                "Understanding input/output flow",
                "Extracting logic",
                "Identifying edge cases"
            ]
        },
        {
            "key": "testcase",
            "title": "Generating Testcases",
            "icon": "⚙️",
            "points": [
                "Creating normal cases",
                "Creating edge cases",
                "Creating boundary cases",
                "Predicting expected outputs"
            ]
        },
        {
            "key": "judge0",
            "title": "Executing on Judge0",
            "icon": "🧪",
            "points": [
                "Compiling submitted code",
                "Running generated testcases",
                "Collecting execution outputs"
            ]
        },
        {
            "key": "validation",
            "title": "Validating Outputs",
            "icon": "🔍",
            "points": [
                "Comparing expected outputs",
                "Checking semantic equivalence",
                "Generating score"
            ]
        },
        {
            "key": "improvement",
            "title": "Improvement Agent",
            "icon": "🛠️",
            "points": [
                "Checking failed testcases",
                "Comparing expected vs actual output",
                "Suggesting better corrected code",
                "Retrying for maximum 2 iterations"
            ]
        }
    ]

    for step in steps:

        if step["key"] in completed_steps:

            status = "completed"
            icon = "✅"

        elif step["key"] == active_step:

            status = "running"
            icon = "🔴"

        else:

            status = "pending"
            icon = "⚪"

        render_status_card(
            step["title"],
            step["points"],
            status=status,
            icon=icon
        )

# =========================================
# MAIN FLOW
# =========================================

if generate_button:

    if not code.strip():

        st.error(
            "Please paste some code."
        )

        st.stop()

    status_placeholder = st.empty()

    # Initial pending state

    with status_placeholder.container():

        render_all_steps(
            active_step=None,
            completed_steps=[]
        )

    time.sleep(0.4)

    # Understanding running

# =========================================
# BACKEND PIPELINE RUNNING
# =========================================

    status_placeholder.empty()

    with status_placeholder.container():

        render_all_steps(
            active_step="validation",
            completed_steps=[
                "understanding",
                "testcase",
                "judge0"
            ]
        )
    # =========================================
    # API CALL
    # =========================================

    try:

        response = requests.post(
            API_URL,
            json={
                "code": code
            },
            timeout=300
        )

        if response.status_code != 200:

            st.error(
                f"API Error: {response.text}"
            )

            st.stop()

        data = response.json()

        if not data.get("success"):

            st.error(
                "Generation failed."
            )

            st.stop()

        # =========================================
        # FINAL COMPLETED STATE
        # =========================================

        status_placeholder.empty()

        with status_placeholder.container():

            render_all_steps(
                active_step=None,
                completed_steps=[
                    "understanding",
                    "testcase",
                    "judge0",
                    "validation",
                    "improvement"
                ]
            )

        # =========================================
        # RESULTS
        # =========================================

        st.divider()

        score = data["score"]

        total = data["total_testcases"]

        results = data["results"]


        original_code = data.get(
            "original_code",
            code
        )

        improved_code = data.get(
            "improved_code",
            original_code
        )

        # =========================================
        # SCORE
        # =========================================

        score_html = f"""
<div class="score-box">
    <div class="score-number">
        {score}/{total}
    </div>
    <div class="score-label">
        Testcases Passed
    </div>
</div>
"""

        st.markdown(
            score_html,
            unsafe_allow_html=True
        )

        # =========================================
        # CODE COMPARISON
        # =========================================

        st.subheader(
            "🛠️ Code Improvement Result"
        )

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                "### Original Code"
            )

            st.code(
                original_code,
                language="java"
            )

        with col2:

            st.markdown(
                "### Improved Code"
            )

            st.code(
                improved_code,
                language="java"
            )

        # =========================================
        # TESTCASE RESULTS
        # =========================================

        st.subheader(
            "🧪 Testcase Results"
        )

        for idx, tc in enumerate(results):

            stdin = tc.get(
                "stdin",
                ""
            )

            expected_output = tc.get(
                "expected_output",
                ""
            )

            actual_output = tc.get(
                "actual_output",
                ""
            )

            passed = tc.get(
                "passed",
                False
            )

            judge0_status = tc.get(
                "status",
                ""
            )

            stderr = tc.get(
                "stderr",
                ""
            )

            compile_output = tc.get(
                "compile_output",
                ""
            )

            with st.container(border=True):

                st.markdown(
                    f"## 🧪 Testcase #{idx + 1}"
                )

                st.markdown(
                    '<div class="label">Input</div>',
                    unsafe_allow_html=True
                )

                st.code(
                    stdin,
                    language="text"
                )

                st.markdown(
                    '<div class="label">Expected Output</div>',
                    unsafe_allow_html=True
                )

                st.code(
                    expected_output,
                    language="text"
                )

                st.markdown(
                    '<div class="label">Judge0 Output</div>',
                    unsafe_allow_html=True
                )

                st.code(
                    actual_output,
                    language="text"
                )

                st.markdown(
                    '<div class="label">Judge0 Status</div>',
                    unsafe_allow_html=True
                )

                st.code(
                    judge0_status,
                    language="text"
                )

                if stderr:

                    st.markdown(
                        '<div class="label">stderr</div>',
                        unsafe_allow_html=True
                    )

                    st.code(
                        stderr,
                        language="text"
                    )

                if compile_output:

                    st.markdown(
                        '<div class="label">Compile Output</div>',
                        unsafe_allow_html=True
                    )

                    st.code(
                        compile_output,
                        language="text"
                    )

                if passed:

                    st.markdown(
                        """
<div class="pass-pill">
✅ PASS
</div>
""",
                        unsafe_allow_html=True
                    )

                else:

                    st.markdown(
                        """
<div class="fail-pill">
❌ FAIL
</div>
""",
                        unsafe_allow_html=True
                    )

                st.divider()

    except Exception as e:

        st.error(
            f"Error: {str(e)}"
        )