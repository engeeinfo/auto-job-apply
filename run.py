import sys
import os

# Append current directory to path so relative imports inside naukri_bot function correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from naukri_bot.main import main

if __name__ == "__main__":
    main()
