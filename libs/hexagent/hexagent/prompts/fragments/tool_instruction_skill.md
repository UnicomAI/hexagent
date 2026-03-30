Execute a skill within the main conversation

When users ask you to perform tasks, check if any of the available skills match. Skills provide specialized capabilities and domain knowledge.

How to invoke:
- Use this tool with the skill name and optional arguments
- Examples:
  - `skill: "pdf"` - invoke the pdf skill
  - `skill: "ms-office-suite:pdf"` - invoke using fully qualified name

Important:
- Available skills are listed in system-reminder messages in the conversation
- When users ask you to perform tasks, check if any of the available skills match.
- **Mandatory for PPT**: For any presentation or slide-related task, you MUST invoke the `pptx` skill first before taking any other action. 
- NEVER mention a skill without actually calling this tool
- Do not invoke a skill that is already running
- If you see a <command-name> tag in the current conversation turn, the skill has ALREADY been loaded - follow the instructions directly instead of calling this tool again
