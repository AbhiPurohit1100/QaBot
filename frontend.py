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

/* cards */

.testcase-card {
    border: 1px solid #31333F;
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 28px;
    background-color: #0E1117;
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
    "LangGraph + Groq + Judge0 powered intelligent testcase validation"
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
    "🚀 Generate & Validate Testcases",
    use_container_width=True
)

# =========================================
# STATUS BOX
# =========================================

def render_status_box(
    title,
    points,
    icon="⏳"
):

    with st.container(border=True):

        st.markdown(
            f"### {icon} {title}"
        )

        for point in points:

            st.write(
                f"• {point}"
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

    # =========================================
    # PLACEHOLDERS
    # =========================================

    understanding_placeholder = st.empty()
    testcase_placeholder = st.empty()
    judge0_placeholder = st.empty()
    validation_placeholder = st.empty()

    # =========================================
    # UNDERSTANDING
    # =========================================

    with understanding_placeholder.container():

        render_status_box(
            "Understanding Code",
            [
                "Detecting programming language",
                "Understanding input/output flow",
                "Extracting business logic",
                "Identifying edge cases"
            ],
            "🧠"
        )

    time.sleep(0.5)

    # =========================================
    # TESTCASE GENERATION
    # =========================================

    with testcase_placeholder.container():

        render_status_box(
            "Generating Intelligent Testcases",
            [
                "Creating normal cases",
                "Creating edge cases",
                "Creating boundary cases",
                "Predicting expected outputs"
            ],
            "⚙️"
        )

    # =========================================
    # JUDGE0
    # =========================================

    with judge0_placeholder.container():

        render_status_box(
            "Executing on Judge0",
            [
                "Compiling submitted code",
                "Running generated testcases",
                "Collecting execution outputs"
            ],
            "⏳"
        )

    # =========================================
    # VALIDATION
    # =========================================

    with validation_placeholder.container():

        render_status_box(
            "Validating Outputs",
            [
                "Comparing expected outputs",
                "Checking semantic equivalence",
                "Generating final score"
            ],
            "⏳"
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
            timeout=240
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
        # UPDATE STATUS
        # =========================================

        understanding_placeholder.empty()

        with understanding_placeholder.container():

            render_status_box(
                "Code Understanding Complete",
                [
                    "Logic analyzed successfully",
                    "Inputs and outputs extracted",
                    "Edge cases identified"
                ],
                "✅"
            )

        testcase_placeholder.empty()

        with testcase_placeholder.container():

            render_status_box(
                "Testcases Generated",
                [
                    "Edge cases generated",
                    "Boundary cases generated",
                    "Expected outputs generated"
                ],
                "✅"
            )

        judge0_placeholder.empty()

        with judge0_placeholder.container():

            render_status_box(
                "Judge0 Execution Complete",
                [
                    "Code compiled successfully",
                    "All testcases executed",
                    "Runtime outputs collected"
                ],
                "✅"
            )

        validation_placeholder.empty()

        with validation_placeholder.container():

            render_status_box(
                "Validation Complete",
                [
                    "Outputs compared",
                    "Semantic validation completed",
                    "Final score generated"
                ],
                "✅"
            )

        # =========================================
        # RESULTS
        # =========================================

        st.divider()

        score = data["score"]

        total = data["total_testcases"]

        results = data["results"]

        # =========================================
        # SCORE
        # =========================================

        score_html = f"""
<div class="score-box">
    <div class="score-number">
        {score}/{total}
    </div>
    Testcases Passed
</div>
"""

        st.markdown(
            score_html,
            unsafe_allow_html=True
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

                # INPUT

                st.markdown(
                    '<div class="label">Input</div>',
                    unsafe_allow_html=True
                )

                st.code(
                    stdin,
                    language="text"
                )

                # EXPECTED OUTPUT

                st.markdown(
                    '<div class="label">Expected Output</div>',
                    unsafe_allow_html=True
                )

                st.code(
                    expected_output,
                    language="text"
                )

                # ACTUAL OUTPUT

                st.markdown(
                    '<div class="label">Judge0 Output</div>',
                    unsafe_allow_html=True
                )

                st.code(
                    actual_output,
                    language="text"
                )

                # STATUS

                st.markdown(
                    '<div class="label">Judge0 Status</div>',
                    unsafe_allow_html=True
                )

                st.code(
                    judge0_status,
                    language="text"
                )

                # STDERR

                if stderr:

                    st.markdown(
                        '<div class="label">stderr</div>',
                        unsafe_allow_html=True
                    )

                    st.code(
                        stderr,
                        language="text"
                    )

                # COMPILE OUTPUT

                if compile_output:

                    st.markdown(
                        '<div class="label">Compile Output</div>',
                        unsafe_allow_html=True
                    )

                    st.code(
                        compile_output,
                        language="text"
                    )

                # PASS FAIL

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