# Engineering Standards

You are working in a mature production codebase. These standards describe how work is expected to be done here. They are not suggestions.

## 1. Code Changes

Scope. Stay narrowly focused on the task you were given. Change what needs changing and nothing else. If you notice an unrelated problem, mention it in your response rather than fixing it.

Readability. Optimize for the next person reading the code, not for cleverness. Simple code beats clever code. If a solution requires a reader to hold more than a few things in their head at once, look for a simpler formulation.

Unused code. Remove unused code completely. Do not leave deprecated stubs, commented-out blocks, or "just in case" branches behind.

Cleanup. After completing the task, you may clean up code that your change touched if it improves clarity. Do not clean up code you did not touch.

## 2. Complexity and Abstraction

Complexity is the primary enemy. It arrives one reasonable-sounding decision at a time, and it is much harder to remove than to add.

Do not abstract until you have seen the same thing three times. The first occurrence is just code. The second may be a coincidence. The third is a pattern. Abstraction built before a pattern is real is speculation, and speculative abstraction almost always turns out to fit nothing.

Abstractions must earn their keep. If an abstraction ends up with one caller, delete it and inline the code.

Prefer concrete over generic. A function with a clear name and concrete types is easier to understand than a generic function with type parameters and callbacks. Generality is a cost, not a feature.

Do not build for imagined futures. Code written for a requirement that never arrives is pure cost. Build what is needed now, in a way that can be extended later if it actually needs to be.

Make the abstraction match the real shape of the problem. An interface designed before you have two real implementations tends to fit neither.

## 3. Dependencies

Every dependency is a long-term commitment. Adding one means accepting its bugs, its security vulnerabilities, its breaking changes, and its transitive dependency tree.

Prefer the standard library. Reach for a third-party package only when the standard library genuinely cannot do the job reasonably.

Apply the fifty-line test. If the functionality can be written clearly in about fifty lines, write it rather than taking on a dependency.

Never add a dependency without being asked. Propose it and explain the tradeoff. Do not add it to the code.

## 4. Refactoring and Blast Radius

Only refactor for a reason. Valid reasons are: the code must change and the current structure makes the change difficult; there is a bug and the confusing structure is what allowed it; or there is a measured performance problem. Invalid reasons are: the code looks ugly but works, you read about a new pattern, or the refactor is more interesting than the actual task.

Respect Chesterton's fence. Before removing or restructuring something that looks pointless, understand why it is there. Code that looks redundant is often guarding a specific edge case. If you cannot determine why it exists, leave it and ask.

Keep changes small. A refactor touching fifty files at once is a disaster waiting to happen.

Do not refactor adjacent code. Code near your change is not part of your change.

## 5. Testing

Test behavior, not implementation. A test should assert what the code does for a caller, not which internal methods were called in which order.

Avoid mock-heavy architectures. If a test needs many mocks to run, that is usually a signal that the design is over-coupled.

Prefer simple tests. A five-hundred-line test with forty mocks does not inspire confidence, because nobody can tell what it actually verifies.

Verify before claiming completion. Run the tests. Confirm the code compiles.

## 6. Performance

Do not optimize prematurely. Make it work, then make it clear, then make it fast only if it is actually slow.

Before optimizing, confirm: is there a measurement showing this is slow, and are users actually affected? If there is no measurement and no complaint, do not optimize.

When optimization is genuinely required, measure first to find the real bottleneck, keep the optimization localized, and add a comment explaining why it is necessary.

## 7. Error Handling

Handle errors that can actually occur. Do not build an elaborate exception taxonomy for a function that has one realistic failure mode.

Let errors propagate when the caller can handle them better. Wrapping every call in a try block with a custom exception type usually obscures the problem.

Distinguish recoverable from unrecoverable. Retry what might succeed. Fail loudly on what will not. Do not silently swallow errors.

## 8. Git and Workflow

Branch hygiene. Work on a branch. Do not commit directly to the main branch.

Commit scope. One logical change per commit. Do not mix a bug fix with a refactor.

Commit messages. Conventional commit format: a type and optional scope, followed by a lowercase imperative subject. Keep the subject under seventy-two characters. No trailing period. No footers, no co-author trailers, no emoji.

Diff review. Before committing, read your own diff. If it contains changes you cannot justify as part of the stated task, remove them.

## 9. Communication

Be direct and concise. State what you did and anything the reader needs to know. No preamble, no restating the request, no summary of what you are about to do.

No filler. Avoid phrases like "I'd be happy to", "Let me go ahead and", and closing offers of further assistance.

Comments. Comments explain why, not what. Reserve comments for non-obvious constraints, business rules, warnings about dangerous changes, or references to external context.

Report problems honestly. If something did not work, say so plainly. Do not describe partial work as complete.
