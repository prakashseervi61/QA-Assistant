"""Chat page — thin wrapper that re-exports the Streamlit multipage page."""

import importlib

# The actual page module has emoji characters in its name, so we use importlib.
_mod = importlib.import_module("src.presentation.streamlit.pages.2_💬_Chat")

main = _mod.main

if __name__ == "__main__":
    main()
