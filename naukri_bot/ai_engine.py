import os
import json
import asyncio
from typing import Dict, Any, Optional, List
from google import genai
from google.genai import types
from groq import Groq

class AIEngine:
    """
    Integrates Gemini AI (primary) and Groq (secondary fallback)
    for job compatibility scoring, application question answering, and resume parsing.
    """
    def __init__(
        self, 
        gemini_key: str = "", 
        groq_key: str = "", 
        gemini_model: str = "gemini-2.5-flash", 
        groq_model: str = "llama-3.3-70b-versatile"
    ):
        self.gemini_key = gemini_key
        self.groq_key = groq_key
        self.gemini_model = gemini_model or "gemini-2.5-flash"
        self.groq_model = groq_model or "llama-3.3-70b-versatile"
        
        # Initialize Gemini client if key is present
        self.gemini_client = None
        if self.gemini_key:
            self.gemini_client = genai.Client(api_key=self.gemini_key)
            
        # Initialize Groq client if key is present
        self.groq_client = Groq(api_key=self.groq_key) if self.groq_key else None

    def update_keys(self, gemini_key: str, groq_key: str) -> None:
        """
        Dynamically update API keys during runtime (e.g. from GUI settings).
        """
        self.gemini_key = gemini_key
        self.groq_key = groq_key
        if self.gemini_key:
            self.gemini_client = genai.Client(api_key=self.gemini_key)
        else:
            self.gemini_client = None
        if self.groq_key:
            self.groq_client = Groq(api_key=self.groq_key)
        else:
            self.groq_client = None

    def _call_gemini_sync(self, prompt: str, enforce_json: bool = False) -> str:
        """
        Synchronous call to Gemini API.
        """
        if not self.gemini_client:
            raise ValueError("Gemini client not initialized. Check API Key configuration.")
            
        config = None
        if enforce_json:
            config = types.GenerateContentConfig(
                response_mime_type="application/json"
            )
            
        response = self.gemini_client.models.generate_content(
            model=self.gemini_model,
            contents=prompt,
            config=config
        )
        return response.text.strip()

    async def _call_gemini(self, prompt: str, enforce_json: bool = False) -> str:
        """
        Asynchronous wrapper to execute the Gemini call in a thread pool.
        """
        return await asyncio.to_thread(self._call_gemini_sync, prompt, enforce_json)

    def _call_groq_sync(self, prompt: str, enforce_json: bool = False) -> str:
        """
        Synchronous call to Groq API.
        """
        if not self.groq_client:
            raise ValueError("Groq API key not configured or invalid.")
        
        kwargs = {
            "messages": [{"role": "user", "content": prompt}],
            "model": self.groq_model
        }
        if enforce_json:
            kwargs["response_format"] = {"type": "json_object"}
            
        chat_completion = self.groq_client.chat.completions.create(**kwargs)
        return chat_completion.choices[0].message.content.strip()

    async def _call_groq(self, prompt: str, enforce_json: bool = False) -> str:
        """
        Asynchronous wrapper to execute the Groq call in a thread pool.
        """
        return await asyncio.to_thread(self._call_groq_sync, prompt, enforce_json)

    async def score_job(self, job_details: Dict[str, Any], resume_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Scores job details against the resume JSON and decides to APPLY or SKIP.
        Returns a dictionary with 'score', 'reason', and 'decision'.
        """
        prompt = f"""
You are an expert AI recruiter. Evaluate the compatibility of the job vacancy and candidate resume.

JOB INFO:
Title: {job_details.get('title', 'N/A')}
Company: {job_details.get('company', 'N/A')}
Required Experience: {job_details.get('experience', 'N/A')}
Location: {job_details.get('location', 'N/A')}
Skills Requested: {job_details.get('skills', [])}

CANDIDATE RESUME PROFILE (JSON):
{json.dumps(resume_data, indent=2)}

Task:
1. Match candidate skills, experience, and title to job requirements.
2. Formulate a match score from 0 to 100.
3. Decide whether the candidate should "APPLY" or "SKIP" (Set decision to "APPLY" if score >= 70, else "SKIP").
4. Provide a brief 1-sentence reason.

Output MUST be a JSON object with the following schema:
{{
  "score": <integer from 0 to 100>,
  "reason": "<string, maximum 25 words>",
  "decision": "<APPLY or SKIP>"
}}
"""
        # Primary: Gemini
        if self.gemini_key:
            try:
                response_text = await self._call_gemini(prompt, enforce_json=True)
                return json.loads(response_text)
            except Exception as e:
                print(f"[AIEngine] Gemini job matching failed: {e}. Falling back to Groq...")

        # Secondary: Groq
        if self.groq_client:
            try:
                response_text = await self._call_groq(prompt, enforce_json=True)
                return json.loads(response_text)
            except Exception as e:
                print(f"[AIEngine] Groq job matching fallback failed: {e}")
                
        # Final fallback
        return {
            "score": 50,
            "reason": "Failed to query AI matching engine. Skipped for safety.",
            "decision": "SKIP"
        }

    async def decide(self, resume_json: dict, job: dict) -> dict:
        """
        Decides whether to apply to the job based on candidate resume and rules.
        """
        prompt = f"""
You are a job application assistant.
Candidate experience: 3.4 years.
Resume summary: {json.dumps(resume_json, indent=2)}

Job Details:
- Title: {job['title']}
- Company: {job['company']}
- Experience Required: {job['experience']}
- Skills: {', '.join(job['skills'])}

Decide if the candidate should apply.
Rules:
1. If required min experience > 4 years → always SKIP
2. If skill overlap < 30% → SKIP
3. If good match → APPLY

Reply ONLY with valid JSON (no markdown):
{{
  "score": <0-100>,
  "reason": "<one sentence>",
  "action": "APPLY" or "SKIP"
}}
"""
        # Primary: Gemini
        if self.gemini_key:
            try:
                response = await self._call_gemini(prompt, enforce_json=True)
                return json.loads(response)
            except Exception as e:
                print(f"[AIEngine] Gemini decide failed: {e}. Falling back to Groq...")

        # Secondary: Groq
        if self.groq_client:
            try:
                response = await self._call_groq(prompt, enforce_json=True)
                return json.loads(response)
            except Exception as e:
                print(f"[AIEngine] Groq decide failed: {e}")

        # Fallback decision
        return {
            "score": 50,
            "reason": "Failed to query AI models for scoring. Skipped for safety.",
            "action": "SKIP"
        }

    async def answer_question(
        self, 
        resume_data: Dict[str, Any], 
        question_text: str, 
        input_type: Any, 
        options: Optional[List[str]] = None
    ) -> str:
        """
        Finds the correct answer to an application form question using context from the resume.
        Supports both signatures:
        1. answer_question(resume_data, question_text, input_type, options)
        2. answer_question(resume_data, question_text, options)
        """
        # Handle signature overload: if input_type is actually options (list)
        if isinstance(input_type, list):
            options = input_type
            input_type = "radio" if options else "text"

        options_clause = f"Options (Select ONLY from this list): {options}" if options else "No pre-defined options (Provide text or numeric input)."
        
        prompt = f"""
You are an assistant completing a job application form. Solve the question accurately using the resume.

CANDIDATE RESUME PROFILE:
{json.dumps(resume_data, indent=2)}

APPLICATION QUESTION:
"{question_text}"

INPUT COMPONENT TYPE:
{input_type}

{options_clause}

Rules:
1. Answer honestly using the facts in the resume.
2. If the question asks for years of experience or Notice Period (and it's not clear), make a reasonable estimate (e.g. 0 to 30 days notice).
3. If options list is given, select the EXACT option that best fits the candidate.
4. Output ONLY the raw answer string. Do not add quotes, markdown formatting, explanations, or pleasantries.

Answer:
"""
        # Primary: Gemini
        if self.gemini_key:
            try:
                answer = await self._call_gemini(prompt, enforce_json=False)
                if answer:
                    return answer
            except Exception as e:
                print(f"[AIEngine] Gemini Q&A failed: {e}. Falling back to Groq...")

        # Secondary: Groq
        if self.groq_client:
            try:
                answer = await self._call_groq(prompt, enforce_json=False)
                if answer:
                    return answer
            except Exception as e:
                print(f"[AIEngine] Groq Q&A fallback failed: {e}")

        # Basic deterministic fallback if all AI models fail
        return self._fallback_qa(question_text, input_type, options)

    def _fallback_qa(self, question: str, input_type: str, options: Optional[List[str]] = None) -> str:
        """
        Fallback logic using regex/keywords when API limit is reached.
        """
        q_clean = question.lower()
        if options:
            if "yes" in q_clean or "no" in q_clean:
                for opt in options:
                    if "yes" in opt.lower():
                        return opt
            return options[0]

        if "notice" in q_clean:
            return "30"
        if "experience" in q_clean or "years" in q_clean:
            return "2"
        if "salary" in q_clean or "ctc" in q_clean:
            return "0"
            
        return "Yes" if input_type == "text" else ""

    async def parse_resume_text(self, raw_text: str) -> Dict[str, Any]:
        """
        Parses raw text extracted from a resume document and outputs a structured JSON profile.
        """
        prompt = f"""
Extract structured details from the following raw resume text.

RAW RESUME TEXT:
{raw_text}

Task:
Parse this resume text into a structured JSON output. Make sure you extract candidate name, email, phone, total experience years, list of key skills, experience history summary, and education details.

Output must follow this schema:
{{
  "name": "<full name>",
  "email": "<email address>",
  "phone": "<phone number>",
  "total_experience_years": <float or integer of estimated total experience>,
  "skills": [<list of strings representing technical and core skills>],
  "experience_summary": "<paragraph summarizing employment timeline and achievements>",
  "education": [
    {{
      "degree": "<degree name>",
      "field": "<major or field>",
      "institution": "<university or school name>"
    }}
  ]
}}
"""
        # Primary: Gemini
        if self.gemini_key:
            try:
                response = await self._call_gemini(prompt, enforce_json=True)
                return json.loads(response)
            except Exception as e:
                print(f"[AIEngine] Gemini resume parse failed: {e}. Falling back to Groq...")

        # Secondary: Groq
        if self.groq_client:
            try:
                response = await self._call_groq(prompt, enforce_json=True)
                return json.loads(response)
            except Exception as e:
                print(f"[AIEngine] Groq resume parse failed: {e}")

        # Empty fallback structure
        return {
            "name": "Unknown Candidate",
            "email": "",
            "phone": "",
            "total_experience_years": 0.0,
            "skills": [],
            "experience_summary": "Parsing failed.",
            "education": []
        }

    async def suggest_target_roles(self, resume_data: Dict[str, Any]) -> str:
        """
        Uses the AI engine to generate 50+ targeted job roles/keywords/synonyms suitable
        for the candidate based on their resume profile (skills, summary, experience).
        Returns a comma-separated string of roles.
        """
        prompt = f"""
You are an expert AI recruiter. Analyze the candidate's resume profile and recommend at least 50 highly specific and generic professional job titles, role keywords, synonyms, and variations that are suitable for them.

CANDIDATE RESUME PROFILE (JSON):
{json.dumps(resume_data, indent=2)}

Task:
Generate a comprehensive list of at least 50 search terms, job titles, or role keywords (separated by commas) that match their expertise. Include:
1. Exact matches for their core title (e.g., Firmware Developer, Embedded Software Engineer).
2. Broad variations (e.g., Software Developer, Software Engineer, Systems Engineer).
3. Skill-based titles (e.g., C++ Developer, FreeRTOS Developer, STM32 Programmer, Microcontroller Engineer).
4. Domain-specific titles (e.g., IoT Firmware Engineer, Embedded Systems Architect).
5. Seniority and related variations (e.g., Member Technical Staff, Technical Specialist, Embedded Associate, Associate Engineer, R&D Engineer).

Return ONLY the raw comma-separated list of at least 50 titles. Do not include markdown, numbering, bullet points, formatting, explanations, or quotes.

Output:
"""
        # Primary: Gemini
        if self.gemini_key:
            try:
                response = await self._call_gemini(prompt, enforce_json=False)
                if response:
                    return response.strip()
            except Exception as e:
                print(f"[AIEngine] Gemini suggest roles failed: {e}. Falling back to Groq...")

        # Secondary: Groq
        if self.groq_client:
            try:
                response = await self._call_groq(prompt, enforce_json=False)
                if response:
                    return response.strip()
            except Exception as e:
                print(f"[AIEngine] Groq suggest roles failed: {e}")

        # Deterministic fallback based on skills/summary keywords
        return "Embedded Software Engineer, Firmware Developer, Embedded Systems Engineer, Software Developer, Software Engineer, C++ Developer, C Developer, Microcontroller Developer, IoT Engineer, FreeRTOS Developer, Firmware Engineer, Embedded Engineer, Systems Engineer, Application Engineer, Hardware Engineer, Systems Software Engineer, Software Programmer, C Programmer, Embedded C Developer, STM32 Developer, ARM Developer, Kernel Developer, Device Driver Developer, Systems Programmer, R&D Engineer, Electronics Engineer, Embedded C Engineer, Firmware Programmer, Product Engineer, Embedded Systems Developer, Controls Engineer, Automation Engineer, Software Associate, Associate Engineer, Embedded Software Designer, Firmware Architect, Embedded Software Programmer, C++ Software Engineer, FreeRTOS Programmer, Microcontroller Specialist, STM32 Firmware Engineer, Real-Time Systems Engineer, RTOS Developer, Bare Metal Developer, Embedded Linux Developer, Systems Integrator, Technical Staff Member, Embedded Systems Designer, Embedded Software Specialist, Software Design Engineer, Firmware R&D Engineer"
