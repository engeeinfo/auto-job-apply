import sys
import os

# Add parent directory to path to import resume_parser
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resume_parser import parse_and_save_resume, RESUME_DATA_FILE

def main():
    resume_path = os.path.join("data", "resume.pdf")
    if not os.path.exists(resume_path):
        print(f"Error: resume file {resume_path} does not exist.")
        sys.exit(1)
        
    print(f"Starting resume parsing for: {resume_path}")
    try:
        data = parse_and_save_resume(resume_path)
        print("Success! Parsed Resume Keys:")
        for k in data.keys():
            if k == "full_extracted_text":
                print(f"  - {k}: length {len(data[k])}")
            else:
                print(f"  - {k}: {type(data[k])}")
    except Exception as e:
        print(f"Failed to parse resume: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
