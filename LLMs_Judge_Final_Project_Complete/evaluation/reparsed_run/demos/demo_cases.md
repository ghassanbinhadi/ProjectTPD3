# Final Test Demo Candidates

## clean_helped

- Interaction: `llama_solver_qwen_critic::gsm8k-test-922`
- Direction: `llama_solver_qwen_critic`
- Solver answer: `6`
- Critic verdict: `INCORRECT`
- Critic proposed answer: `60`
- Revised answer: `60`
- Gold answer: `60`
- Transition: `HELPED`
- Why: The Solver was wrong, the Critic correctly disagreed, and revision changed the answer to the gold value.

**Question:** Martha has been collecting shells since she turned 5 years old, every month she collects one shell. By her 10th birthday, how many shells will Martha have collected?

## false_alarm_hurt

- Interaction: `qwen_solver_llama_critic::gsm8k-test-252`
- Direction: `qwen_solver_llama_critic`
- Solver answer: `73`
- Critic verdict: `INCORRECT`
- Critic proposed answer: `82`
- Revised answer: `82`
- Gold answer: `73`
- Transition: `HURT`
- Why: The Solver was correct, the Critic incorrectly disagreed, and revision changed the answer away from the gold value.

**Question:** Last night Rick killed ten wolves and 15 cougars while hunting. Today Rick killed three times as many wolves as cougars and three fewer cougars than the previous night. How many animals did Rick kill?
