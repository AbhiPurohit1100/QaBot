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
# SESSION STATE
# =========================================

if "dependency_files" not in st.session_state:

    st.session_state.dependency_files = [
        {
            "filename": "middleware/auth.js",
            "code": ""
        }
    ]

# =========================================
# CSS
# =========================================

st.markdown("""
<style>

.block-container {
    max-width: 1250px;
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

.info-pill {
    display: inline-block;
    background-color: #172554;
    color: #93c5fd;
    padding: 8px 14px;
    border-radius: 999px;
    font-weight: 700;
    margin-bottom: 16px;
}

.context-box {
    border: 1px solid #374151;
    border-radius: 16px;
    padding: 18px;
    margin-bottom: 18px;
    background-color: #0E1117;
}

.small-muted {
    color: #9ca3af;
    font-size: 14px;
}

.explanation-box {
    padding: 24px;
    border-radius: 18px;
    background-color: #111827;
    border: 1px solid #374151;
    margin-top: 24px;
    margin-bottom: 30px;
}

.explanation-title {
    font-size: 22px;
    font-weight: 800;
    margin-bottom: 12px;
    color: #ffffff;
}

.explanation-text {
    color: #d1d5db;
    font-size: 16px;
    line-height: 1.7;
}

</style>
""", unsafe_allow_html=True)

# =========================================
# HEADER
# =========================================

st.title("🧠 AI Testcase Generator")

st.caption(
    "LangGraph + Groq + Judge0 powered testcase validation, language detection, code improvement, and failure explanation"
)

# =========================================
# DEFAULT CODE
# =========================================

default_code = """const fs = require("fs");

const input = fs.readFileSync(0, "utf-8").trim().split(/\\s+/);

const email = input[0];
const password = input[1];

const validEmail = "test@example.com";
const validPassword = "password123";

if (!email || !password) {
    console.log("Missing email or password");
} else if (email === validEmail && password === validPassword) {
    console.log("Login successful");
} else {
    console.log("Invalid credentials");
}
"""

# =========================================
# HELPERS
# =========================================

def add_dependency_file():

    st.session_state.dependency_files.append(
        {
            "filename": f"dependency_{len(st.session_state.dependency_files) + 1}.js",
            "code": ""
        }
    )


def remove_dependency_file(index):

    if len(st.session_state.dependency_files) > 1:

        st.session_state.dependency_files.pop(index)

    else:

        st.session_state.dependency_files[0] = {
            "filename": "middleware/auth.js",
            "code": ""
        }


def build_context_string():

    context_parts = []

    for dep in st.session_state.dependency_files:

        filename = dep.get(
            "filename",
            ""
        ).strip()

        dep_code = dep.get(
            "code",
            ""
        ).strip()

        if not filename and not dep_code:

            continue

        context_parts.append(
            f"""
==============================
FILE: {filename if filename else "unnamed_dependency"}
==============================

{dep_code}
"""
        )

    return "\n".join(context_parts).strip()


# =========================================
# INPUT SECTION
# =========================================

st.subheader("📌 Main Code")

code = st.text_area(
    "Paste the main code that should be executed by Judge0",
    value=default_code,
    height=350
)

st.caption(
    "This is the only code that Judge0 executes. Dependency files below are used as extra context for better testcase generation and code suggestion."
)

st.divider()

# =========================================
# DEPENDENCY CONTEXT SECTION
# =========================================

st.subheader("📎 Dependency / Context Files")

st.caption(
    "Add middleware, controllers, routes, validators, models, helpers, or any related files here. These are not executed by Judge0; they help the AI understand the full behavior."
)

top_col1, top_col2 = st.columns([1, 4])

with top_col1:

    st.button(
        "➕ Add Dependency File",
        on_click=add_dependency_file,
        use_container_width=True
    )

with top_col2:

    st.markdown(
        '<div class="small-muted">You can add multiple dependency code blocks. Each block will be sent to backend as context.</div>',
        unsafe_allow_html=True
    )

for index, dep in enumerate(st.session_state.dependency_files):

    with st.container(border=True):

        st.markdown(
            f"### Dependency File #{index + 1}"
        )

        filename_key = f"dependency_filename_{index}"
        code_key = f"dependency_code_{index}"

        filename = st.text_input(
            "File name / path",
            value=dep.get("filename", ""),
            key=filename_key,
            placeholder="example: controllers/authController.js"
        )

        dep_code = st.text_area(
            "Dependency code",
            value=dep.get("code", ""),
            key=code_key,
            height=220,
            placeholder="""Example:

// validators/emailValidator.js
function isValidEmail(email) {
    return email.includes("@") && email.includes(".");
}

module.exports = isValidEmail;
"""
        )

        st.session_state.dependency_files[index]["filename"] = filename
        st.session_state.dependency_files[index]["code"] = dep_code

        remove_col1, remove_col2 = st.columns([1, 5])

        with remove_col1:

            if st.button(
                "🗑️ Remove",
                key=f"remove_dependency_{index}",
                use_container_width=True
            ):

                remove_dependency_file(index)
                st.rerun()

        with remove_col2:

            if dep_code.strip():

                st.success(
                    "Dependency context added."
                )

            else:

                st.info(
                    "Optional. Leave empty if not needed."
                )

context = build_context_string()

with st.expander("👀 Preview Combined Context Sent To Backend"):

    if context.strip():

        st.code(
            context,
            language="text"
        )

    else:

        st.info(
            "No dependency context added yet."
        )

st.divider()

# =========================================
# BUTTON
# =========================================

generate_button = st.button(
    "🚀 Generate, Validate & Suggest Improved Code",
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
            "title": "Understanding Code + Context",
            "points": [
                "Reading main code",
                "Reading dependency files",
                "Understanding input/output flow",
                "Identifying edge cases"
            ]
        },
        {
            "key": "language",
            "title": "Detecting Language",
            "points": [
                "Using rule-based detection",
                "Using AI fallback if needed",
                "Mapping to Judge0 language ID"
            ]
        },
        {
            "key": "testcase",
            "title": "Generating Testcases",
            "points": [
                "Creating normal cases",
                "Creating edge cases",
                "Using dependency context",
                "Predicting expected outputs"
            ]
        },
        {
            "key": "judge0",
            "title": "Executing on Judge0",
            "points": [
                "Compiling submitted code",
                "Running generated testcases",
                "Collecting execution outputs"
            ]
        },
        {
            "key": "validation",
            "title": "Validating Outputs",
            "points": [
                "Comparing expected outputs",
                "Checking semantic equivalence",
                "Generating score"
            ]
        },
        {
            "key": "improvement",
            "title": "Improvement Agent",
            "points": [
                "Reading failed testcases",
                "Using dependency context",
                "Comparing expected vs actual output",
                "Suggesting one improved code version"
            ]
        },
        {
            "key": "explanation",
            "title": "Failure Explanation",
            "points": [
                "Checking failed testcases",
                "Explaining why failures happened",
                "Explaining how improved code fixes them"
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
            "Please paste some main code."
        )

        st.stop()

    status_placeholder = st.empty()

    # Initial pending state

    with status_placeholder.container():

        render_all_steps(
            active_step=None,
            completed_steps=[]
        )

    time.sleep(0.3)

    # Since backend is one blocking request, we cannot know exact live step.
    # This is the most honest UI state during the actual request.

    status_placeholder.empty()

    with status_placeholder.container():

        render_all_steps(
            active_step="validation",
            completed_steps=[
                "understanding",
                "language",
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
                "code": code,
                "context": context
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
                    "language",
                    "testcase",
                    "judge0",
                    "validation",
                    "improvement",
                    "explanation"
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

        explanation = data.get(
            "explanation",
            ""
        )

        detected_language = data.get(
            "detected_language",
            "unknown"
        )

        language_id = data.get(
            "language_id",
            "unknown"
        )

        returned_context = data.get(
            "context",
            context
        )

        # =========================================
        # LANGUAGE INFO
        # =========================================

        st.markdown(
            f"""
<div class="info-pill">
    Detected Language: {detected_language} | Judge0 ID: {language_id}
</div>
""",
            unsafe_allow_html=True
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
        # CONTEXT USED
        # =========================================

        if returned_context.strip():

            with st.expander("📎 Dependency Context Used"):

                st.code(
                    returned_context,
                    language="text"
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
                language=detected_language if detected_language != "unknown" else "text"
            )

        with col2:

            st.markdown(
                "### Suggested Improved Code"
            )

            st.code(
                improved_code,
                language=detected_language if detected_language != "unknown" else "text"
            )

        # =========================================
        # EXPLANATION SECTION
        # =========================================

        st.subheader(
            "📘 Failure Explanation & Improvement Summary"
        )

        if explanation.strip():

            st.markdown(
                f"""
<div class="explanation-box">
    <div class="explanation-title">
        What happened?
    </div>
    <div class="explanation-text">
        {explanation.replace(chr(10), "<br>")}
    </div>
</div>
""",
                unsafe_allow_html=True
            )

        else:

            st.info(
                "No explanation returned."
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

            message = tc.get(
                "message",
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

                if message:

                    st.markdown(
                        '<div class="label">Judge0 Message</div>',
                        unsafe_allow_html=True
                    )

                    st.code(
                        message,
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