import unittest
from unittest.mock import patch, MagicMock
import os
import tempfile
import shutil

# Import the modules we want to test
from resume_parser import extract_json_from_response, extract_text_from_file
from ai_matcher import parse_score
import settings
import job_scraper

class TestResumeParser(unittest.TestCase):
    def setUp(self):
        import resume_parser
        resume_parser.clear_cache()

    def tearDown(self):
        import resume_parser
        resume_parser.clear_cache()

    def test_clean_json(self):
        input_text = '{"name": "John Doe", "total_years_experience": 5}'
        expected = {"name": "John Doe", "total_years_experience": 5}
        self.assertEqual(extract_json_from_response(input_text), expected)

    def test_markdown_json_block(self):
        input_text = '```json\n{"name": "John Doe", "total_years_experience": 5}\n```'
        expected = {"name": "John Doe", "total_years_experience": 5}
        self.assertEqual(extract_json_from_response(input_text), expected)

    def test_markdown_raw_block(self):
        input_text = '```\n{"name": "John Doe", "total_years_experience": 5}\n```'
        expected = {"name": "John Doe", "total_years_experience": 5}
        self.assertEqual(extract_json_from_response(input_text), expected)

    def test_surrounding_text_json(self):
        input_text = 'Response data is:\n```json\n{"name": "Jane", "total_years_experience": 3}\n```\nEnd of response.'
        expected = {"name": "Jane", "total_years_experience": 3}
        self.assertEqual(extract_json_from_response(input_text), expected)

    def test_python_dict_fallback(self):
        # Test parsing when AI returns Python dict representation with single quotes
        input_text = "Here is your dict: {'name': 'John Doe', 'skills': ['Python', 'Git']}"
        expected = {"name": "John Doe", "skills": ["Python", "Git"]}
        self.assertEqual(extract_json_from_response(input_text), expected)

    def test_invalid_json_raises_error(self):
        input_text = "Invalid text with no braces"
        with self.assertRaises(ValueError):
            extract_json_from_response(input_text)

    @patch('resume_parser.docx.Document')
    def test_docx_extraction(self, mock_document):
        # Setup mock sections, paragraphs, tables
        mock_doc_instance = MagicMock()
        
        # Mock paragraph
        p1 = MagicMock()
        p1.text = "Hello Paragraph"
        mock_doc_instance.paragraphs = [p1]
        
        # Mock header & footer in section
        sec = MagicMock()
        h_p = MagicMock()
        h_p.text = "Header Info"
        sec.header.paragraphs = [h_p]
        
        f_p = MagicMock()
        f_p.text = "Footer Info"
        sec.footer.paragraphs = [f_p]
        mock_doc_instance.sections = [sec]
        
        # Mock table with cells and paragraphs
        cell_p = MagicMock()
        cell_p.text = "Cell Text"
        cell = MagicMock()
        cell.paragraphs = [cell_p]
        cell.text = "Cell Text"
        row = MagicMock()
        row.cells = [cell]
        table = MagicMock()
        table.rows = [row]
        mock_doc_instance.tables = [table]
        
        mock_document.return_value = mock_doc_instance
        
        extracted = extract_text_from_file("dummy.docx")
        
        self.assertIn("Header Info", extracted)
        self.assertIn("Hello Paragraph", extracted)
        self.assertIn("Cell Text", extracted)
        self.assertIn("Footer Info", extracted)

    def test_calculate_file_hash(self):
        from resume_parser import calculate_file_hash
        # Create a temp file and test if it returns correct MD5
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"Hello world hashing test!")
            tmp_path = tmp.name
        try:
            h = calculate_file_hash(tmp_path)
            self.assertIsNotNone(h)
            self.assertEqual(h, "d194a7aee888a14a6ec8fc5387ee98c4")  # md5 of "Hello world hashing test!"
        finally:
            os.remove(tmp_path)

    @patch('resume_parser.calculate_file_hash')
    @patch('resume_parser.load_settings')
    @patch('resume_parser.extract_text_from_file')
    @patch('resume_parser.parse_resume_with_gemini')
    def test_parse_and_save_resume_cache(self, mock_gemini, mock_extract, mock_settings, mock_hash):
        import json
        from resume_parser import parse_and_save_resume, CACHE_VERSION
        
        mock_hash.return_value = "cached_hash_123"
        mock_settings.return_value = {"gemini_api_key": "some_key"}
        mock_extract.return_value = "some text"
        mock_gemini.return_value = {"name": "Cached Candidate", "file_hash": "cached_hash_123", "cache_version": CACHE_VERSION}
        
        import resume_parser
        old_data_file = resume_parser.RESUME_DATA_FILE
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            resume_parser.RESUME_DATA_FILE = tmp.name
            
        try:
            # First, write a dummy cached data into RESUME_DATA_FILE matching hash and cache_version
            cached_json = {"name": "Cached Candidate", "file_hash": "cached_hash_123", "cache_version": CACHE_VERSION}
            with open(resume_parser.RESUME_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(cached_json, f)
                
            # Now call parse_and_save_resume. It should return cached results instantly
            res = parse_and_save_resume("dummy.pdf")
            
            self.assertEqual(res["name"], "Cached Candidate")
            mock_extract.assert_not_called()
            mock_gemini.assert_not_called()
            
        finally:
            os.remove(resume_parser.RESUME_DATA_FILE)
            resume_parser.RESUME_DATA_FILE = old_data_file

    @patch('resume_parser.calculate_file_hash')
    @patch('resume_parser.load_settings')
    @patch('resume_parser.extract_text_from_file')
    @patch('resume_parser.parse_resume_with_gemini')
    def test_parse_and_save_resume_cache_invalid_version(self, mock_gemini, mock_extract, mock_settings, mock_hash):
        import json
        from resume_parser import parse_and_save_resume, CACHE_VERSION
        
        mock_hash.return_value = "cached_hash_123"
        mock_settings.return_value = {"gemini_api_key": "some_key"}
        mock_extract.return_value = "some text"
        mock_gemini.return_value = {"name": "New parsed candidate", "file_hash": "cached_hash_123", "cache_version": CACHE_VERSION}
        
        import resume_parser
        old_data_file = resume_parser.RESUME_DATA_FILE
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            resume_parser.RESUME_DATA_FILE = tmp.name
            
        try:
            # Write a cached JSON with an OUTDATED cache_version ("v1")
            cached_json = {"name": "Cached Candidate", "file_hash": "cached_hash_123", "cache_version": "v1"}
            with open(resume_parser.RESUME_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(cached_json, f)
                
            # Now call parse_and_save_resume. It should bypass the outdated cache, and call extraction and Gemini parser!
            res = parse_and_save_resume("dummy.pdf")
            
            self.assertEqual(res["name"], "New parsed candidate")
            mock_extract.assert_called_once()
            mock_gemini.assert_called_once()
            
        finally:
            os.remove(resume_parser.RESUME_DATA_FILE)
            resume_parser.RESUME_DATA_FILE = old_data_file

    def test_parse_exp_less_than_4(self):
        from auto_applier import parse_exp_less_than_4
        self.assertTrue(parse_exp_less_than_4("0 - 3 years"))
        self.assertTrue(parse_exp_less_than_4("1-4 Yrs"))
        self.assertFalse(parse_exp_less_than_4("4 - 9 Yrs"))
        self.assertFalse(parse_exp_less_than_4("5 Yrs"))
        self.assertTrue(parse_exp_less_than_4("N/A"))

    @patch('auto_applier.call_ai_brief')
    @patch('auto_applier.load_settings')
    def test_get_ai_apply_decision(self, mock_load, mock_ai_brief):
        from auto_applier import get_ai_apply_decision
        mock_load.return_value = {
            "gemini_api_key": "some_key",
            "grok_api_key": "",
            "target_roles": "Software Engineer, C++ Developer"
        }
        
        mock_ai_brief.return_value = "apply"
        self.assertEqual(get_ai_apply_decision({"target_roles": ["Backend Developer"]}, "Software Engineer", "Google", "2 Yrs", "some_key"), "apply")
        
        mock_ai_brief.return_value = "not apply"
        self.assertEqual(get_ai_apply_decision({"target_roles": ["Backend Developer"]}, "Software Engineer", "Google", "2 Yrs", "some_key"), "not apply")

    @patch('auto_applier.session')
    def test_call_gemini_brief(self, mock_session):
        from auto_applier import call_gemini_brief
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "apply"
                    }]
                }
            }]
        }
        mock_session.post.return_value = mock_response
        
        res = call_gemini_brief("some prompt", "some_key")
        self.assertEqual(res, "apply")
        mock_session.post.assert_called_once()

    @patch('resume_parser.calculate_file_hash')
    @patch('resume_parser.load_settings')
    @patch('resume_parser.extract_text_from_file')
    @patch('resume_parser.parse_resume_with_gemini')
    def test_persistent_and_memory_caching(self, mock_gemini, mock_extract, mock_settings, mock_hash):
        import json
        from resume_parser import parse_and_save_resume, CACHE_VERSION
        import resume_parser
        
        # Scenario: Two different resumes
        # Resume 1
        hash1 = "hash_resume_1"
        data1 = {"name": "Candidate One", "file_hash": hash1, "cache_version": CACHE_VERSION}
        # Resume 2
        hash2 = "hash_resume_2"
        data2 = {"name": "Candidate Two", "file_hash": hash2, "cache_version": CACHE_VERSION}
        
        mock_settings.return_value = {"gemini_api_key": "some_key"}
        mock_extract.return_value = "extracted text content"
        
        # Temp files for tests
        old_data_file = resume_parser.RESUME_DATA_FILE
        old_cache_file = resume_parser.RESUME_CACHE_FILE
        
        temp_data_fd, temp_data_path = tempfile.mkstemp()
        temp_cache_fd, temp_cache_path = tempfile.mkstemp()
        os.close(temp_data_fd)
        os.close(temp_cache_fd)
        
        resume_parser.RESUME_DATA_FILE = temp_data_path
        resume_parser.RESUME_CACHE_FILE = temp_cache_path
        
        try:
            # 1. Parse Resume 1 (should call API)
            mock_hash.return_value = hash1
            mock_gemini.return_value = data1
            
            res1 = parse_and_save_resume("resume1.pdf")
            self.assertEqual(res1["name"], "Candidate One")
            self.assertEqual(mock_gemini.call_count, 1)
            
            # 2. Parse Resume 2 (should call API)
            mock_hash.return_value = hash2
            mock_gemini.return_value = data2
            
            res2 = parse_and_save_resume("resume2.pdf")
            self.assertEqual(res2["name"], "Candidate Two")
            self.assertEqual(mock_gemini.call_count, 2)
            
            # 3. Parse Resume 1 again. It is no longer the active resume on disk (since Resume 2 was written to RESUME_DATA_FILE)
            # But it should load instantly from in-memory cache!
            mock_hash.return_value = hash1
            mock_gemini.reset_mock()
            mock_extract.reset_mock()
            
            res1_cached = parse_and_save_resume("resume1.pdf")
            self.assertEqual(res1_cached["name"], "Candidate One")
            mock_gemini.assert_not_called()
            mock_extract.assert_not_called()
            
            # 4. Clear in-memory cache manually to force loading from the persistent multi-resume cache file (RESUME_CACHE_FILE)
            resume_parser._IN_MEMORY_CACHE.clear()
            
            res1_persistent = parse_and_save_resume("resume1.pdf")
            self.assertEqual(res1_persistent["name"], "Candidate One")
            mock_gemini.assert_not_called()
            mock_extract.assert_not_called()
            
        finally:
            os.remove(temp_data_path)
            os.remove(temp_cache_path)
            resume_parser.RESUME_DATA_FILE = old_data_file
            resume_parser.RESUME_CACHE_FILE = old_cache_file

    @patch('resume_parser.session')
    def test_gemini_api_error_handling(self, mock_session):
        from resume_parser import parse_resume_with_gemini
        
        # Test 401/403 PermissionError should raise PermissionError immediately and not loop/sleep
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_session.post.return_value = mock_response
        
        with self.assertRaises(PermissionError):
            parse_resume_with_gemini("some text", "some_key")
        # Should fail on the first model, first attempt, and raise immediately (1 post call)
        self.assertEqual(mock_session.post.call_count, 1)
        
        # Test 404/400 bad request/model not found should break out of the attempts loop immediately
        # and try the next model. With 5 models in list, it will call post 5 times (once per model) instead of 10 times
        mock_session.post.reset_mock()
        mock_response.status_code = 404
        mock_response.text = "Model Not Found"
        
        with self.assertRaises(Exception):
            parse_resume_with_gemini("some text", "some_key")
            
        self.assertEqual(mock_session.post.call_count, 5)


class TestAiMatcher(unittest.TestCase):
    def test_parse_score_int(self):
        res = {"score": 85, "reason": "Good match"}
        self.assertEqual(parse_score(res), 85.0)

    def test_parse_score_float(self):
        res = {"score": 85.5, "reason": "Good match"}
        self.assertEqual(parse_score(res), 85.5)

    def test_parse_score_string_numeric(self):
        res = {"score": "75", "reason": "Good match"}
        self.assertEqual(parse_score(res), 75.0)

    def test_parse_score_string_percent(self):
        res = {"score": "80%", "reason": "Good match"}
        self.assertEqual(parse_score(res), 80.0)

    def test_parse_score_string_complex(self):
        res = {"score": "Overall match score is 95 out of 100", "reason": "Good match"}
        self.assertEqual(parse_score(res), 95.0)

    def test_parse_score_invalid_raises_error(self):
        res = {"score": "no score", "reason": "Good match"}
        with self.assertRaises(ValueError):
            parse_score(res)

        res_missing = {"reason": "Good match"}
        with self.assertRaises(ValueError):
            parse_score(res_missing)

    @patch('ai_matcher.requests.post')
    def test_call_grok_score_groq_routing(self, mock_post):
        from ai_matcher import call_grok_score
        
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"score": 90, "reason": "Llama 3 match"}'
                }
            }]
        }
        mock_post.return_value = mock_response
        
        # Case 1: Groq Key starting with gsk_
        res = call_grok_score({"name": "Test"}, {"title": "Engineer"}, "gsk_testkey")
        self.assertEqual(res["score"], 90)
        # Verify it went to Groq URL with JSON format and Groq model
        mock_post.assert_called_with(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Content-Type": "application/json", "Authorization": "Bearer gsk_testkey"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": mock_post.call_args[1]["json"]["messages"][0]["content"]}],
                "response_format": {"type": "json_object"}
            },
            timeout=25
        )
        
        # Case 2: xAI Grok Key
        mock_post.reset_mock()
        res = call_grok_score({"name": "Test"}, {"title": "Engineer"}, "xai-testkey")
        self.assertEqual(res["score"], 90)
        # Verify it went to xAI URL with Grok model and no JSON response_format
        mock_post.assert_called_with(
            "https://api.x.ai/v1/chat/completions",
            headers={"Content-Type": "application/json", "Authorization": "Bearer xai-testkey"},
            json={
                "model": "grok-4.3",
                "messages": [{"role": "user", "content": mock_post.call_args[1]["json"]["messages"][0]["content"]}],
            },
            timeout=25
        )


class TestSettings(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test settings
        self.test_dir = tempfile.mkdtemp()
        self.old_data_dir = settings.DATA_DIR
        self.old_settings_file = settings.SETTINGS_FILE
        settings.DATA_DIR = self.test_dir
        settings.SETTINGS_FILE = os.path.join(self.test_dir, "settings.json")

    def tearDown(self):
        # Clean up temporary directory
        shutil.rmtree(self.test_dir)
        settings.DATA_DIR = self.old_data_dir
        settings.SETTINGS_FILE = self.old_settings_file

    def test_load_default_settings(self):
        # File doesn't exist yet, should return defaults
        data = settings.load_settings()
        self.assertEqual(data["target_roles"], "Python Developer, Backend Engineer")
        self.assertEqual(data["min_match_score"], 70)
        self.assertEqual(data["enabled_boards"], ["Naukri"])

    def test_save_and_load_settings(self):
        custom_settings = {
            "gemini_api_key": "test_gemini_key",
            "grok_api_key": "test_grok_key",
            "target_roles": "Data Scientist",
            "min_match_score": 85,
            "enabled_boards": ["Naukri", "Indeed"]
        }
        success = settings.save_settings(custom_settings)
        self.assertTrue(success)
        
        loaded = settings.load_settings()
        self.assertEqual(loaded["target_roles"], "Data Scientist")
        self.assertEqual(loaded["min_match_score"], 85)
        self.assertEqual(loaded["gemini_api_key"], "test_gemini_key")
        self.assertEqual(loaded["enabled_boards"], ["Naukri", "Indeed"])


class TestJobScraper(unittest.TestCase):
    def test_chrome_version_call_safety(self):
        # Ensure that running the registry major version query executes without throwing exceptions
        # (It will return an int, None, or raise nothing on Windows systems)
        try:
            version = job_scraper.get_chrome_major_version()
            if version is not None:
                self.assertIsInstance(version, int)
        except Exception as e:
            self.fail(f"get_chrome_major_version raised an unexpected exception: {e}")

class TestAIFallbacks(unittest.TestCase):
    @patch('auto_applier.session')
    @patch('auto_applier.load_settings')
    def test_call_ai_brief_circular_fallback(self, mock_load, mock_session):
        from auto_applier import call_ai_brief
        
        # Configure settings to return both keys
        mock_load.return_value = {
            "gemini_api_key": "gemini-key",
            "grok_api_key": "gsk_groq-key"
        }
        
        # Scenario 1: primary_engine="gemini"
        # Gemini calls fail (status 404), Groq succeeds (status 200)
        gemini_response = MagicMock()
        gemini_response.status_code = 404
        
        grok_response = MagicMock()
        grok_response.status_code = 200
        grok_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Grok result text"
                }
            }]
        }
        
        # 4 gemini models to try, then 1 grok model
        mock_session.post.side_effect = [gemini_response, gemini_response, gemini_response, gemini_response, grok_response]
        
        res = call_ai_brief("prompt", None, primary_engine="gemini")
        self.assertEqual(res, "Grok result text")
        
        # Scenario 2: primary_engine="grok"
        # Groq calls fail (status 404), Gemini succeeds (status 200)
        mock_session.post.reset_mock()
        grok_fail_response = MagicMock()
        grok_fail_response.status_code = 404
        
        gemini_ok_response = MagicMock()
        gemini_ok_response.status_code = 200
        gemini_ok_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "Gemini result text"
                    }]
                }
            }]
        }
        
        # 4 groq models to try, then 1 gemini model
        mock_session.post.side_effect = [grok_fail_response, grok_fail_response, grok_fail_response, grok_fail_response, gemini_ok_response]
        
        res = call_ai_brief("prompt", None, primary_engine="grok")
        self.assertEqual(res, "Gemini result text")

    @patch('ai_matcher.call_gemini_score')
    @patch('ai_matcher.call_grok_score')
    @patch('ai_matcher.load_settings')
    def test_score_job_match_fallback(self, mock_load, mock_grok, mock_gemini):
        from ai_matcher import score_job_match
        
        # Configure keys
        mock_load.return_value = {
            "gemini_api_key": "gemini-key",
            "grok_api_key": "gsk_groq-key",
            "min_match_score": 70
        }
        
        # Scenario: Gemini fails, Grok succeeds
        mock_gemini.side_effect = Exception("Gemini down")
        mock_grok.return_value = {"score": 85, "reason": "Good match"}
        
        res = score_job_match({"skills": ["Python"]}, {"title": "Developer"})
        self.assertEqual(res["score"], 85.0)
        self.assertTrue(res["qualified"])
        self.assertIn("Grok (85%)", res["reasons"])
class TestVisualActionRecorder(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_recorder_generation(self):
        from action_recorder import VisualActionRecorder
        # Instantiate recorder without a driver
        recorder = VisualActionRecorder(driver=None, session_name="Test_Session", base_dir=self.test_dir)
        
        # Log a step
        recorder.record_action("Launch", "Browser launched successfully", capture_screenshot=False)
        self.assertEqual(len(recorder.steps), 1)
        self.assertEqual(recorder.steps[0]["action"], "Launch")
        
        # Verify JSON log file exists
        log_json_path = os.path.join(recorder.session_dir, "recording_log.json")
        self.assertTrue(os.path.exists(log_json_path))
        
        # Generate HTML report
        report_path = recorder.generate_report()
        self.assertTrue(os.path.exists(report_path))
        
        # Read HTML report and verify content
        with open(report_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Visual Automation Execution Report", html)
        self.assertIn("Browser launched successfully", html)

if __name__ == '__main__':
    unittest.main()
