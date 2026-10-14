"""The home assistant: one request, answered across Nexus's pillars.

    START -> user_context -> conversation
                               |-- small talk or help -> respond -> END
                               '-- task -> guardrails -> understand -> governance -> route
                                       -> prompts | marketplace | learning | community   parallel fan-out
                                       -> synthesize                                      fan-in
                                       -> save -> END

WHO is asking        user_context  UserContext, from the directory and SQL
TALK or TASK         conversation  greetings, thanks, goodbyes and help answered
                                   directly; a greeting in front of a task set aside
WHAT they may see    guardrails  security, data and policy: entitlements, the
  and send           request's sensitivity, what the model may receive
WHAT they are doing  understand  TaskContext: intents, objective, job
WHICH capabilities   understand, route  pillars and a query written for each
POLICY on the plan   governance  allowed pillars and jobs, what each pillar is asked

The model plans every task (understand), judges each pillar agent's shortlist
(prompts, marketplace, learning), and writes the reply (synthesize), within
what the data policy lets it see; rules stand in only where it may not or
cannot be asked. Nothing is cached: every request is read afresh. Streamed,
the answer arrives event by event (router.py).
"""
