"""Frozen prompts for the solver, critic, and revision stages."""

PROMPT_VERSION = "V6"

SOLVER_PROMPT = """Solve the following problem step by step. Then give your final answer on a new line in exactly this format:
FINAL_ANSWER: <number>
Problem:
{question}"""

CRITIC_INDEPENDENT_PROMPT = SOLVER_PROMPT

CRITIQUE_PROMPT = """You independently solved a math problem and reached your own answer. Another model solved the same problem.
Compare and decide whether the other model's final answer is correct.
Problem:
{question}
Your own solution:
{critic_reasoning}
Your own final answer: {critic_answer}
The other model's final answer: {solver_answer}
Respond in exactly this format:
VERDICT: CORRECT or INCORRECT
ERROR_DESCRIPTION: <if incorrect, briefly explain the likely error; if correct, write "none">
PROPOSED_ANSWER: <your final answer>"""

REVISION_PROMPT = """Another model independently solved this problem and believes your answer is incorrect.
Its reasoning: {error_description}
Its proposed answer: {proposed_answer}.
Reconsider your solution. You may KEEP your original answer if you still believe it is correct, or CHANGE it if you find a real error. Do not change just because you were challenged.
Problem:
{question}
Your original answer: {solver_answer}
Briefly explain whether the critique revealed a real error, then output:
REASONING: <brief explanation>
DECISION: KEEP or CHANGE
FINAL_ANSWER: <number>"""

PROMPTS = {
    "solver": SOLVER_PROMPT,
    "critic_independent": CRITIC_INDEPENDENT_PROMPT,
    "critique": CRITIQUE_PROMPT,
    "revision": REVISION_PROMPT,
}


def render_prompt(stage: str, **values: str) -> str:
    """Render one fixed prompt without altering its wording or format."""
    return PROMPTS[stage].format(**values)
