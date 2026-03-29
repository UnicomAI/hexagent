The PresentToUser tool makes files visible to the user for viewing and rendering in the client interface.

When to use:
- Making any file available for the user to view, download, or interact with
- Presenting multiple related files at once
- After creating a file that should be presented to the user

When NOT to use:
- When you only need to read file contents for your own processing
- For temporary or intermediate files not meant for user viewing

How it works:
- Accepts an array of file paths from the container filesystem
- Returns output paths where files can be accessed by the client
- Output paths are returned in the same order as input file paths
- Multiple files can be presented efficiently in a single call
- If a file is not in the output directory, it will be automatically copied into that directory
- The first input path passed in to the PresentToUser tool, and therefore the first output path returned from it, should correspond to the file that is most relevant for the user to see first
- In the same turn, do not call PresentToUser repeatedly for the same file path. If the file list is unchanged, reuse the existing result instead of presenting it again
