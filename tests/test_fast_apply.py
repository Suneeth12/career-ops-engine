import os
import shutil
import tempfile
import pytest

from scripts.fast_apply import run_fast_apply
from tools import common
from tools.tailorer import PageValidator


def test_fast_apply_referral_text_execution():
    text = (
        "Company - QuickTest Inc\n"
        "Role - Machine Learning Engineer\n"
        "Batch - 2026\n"
        "Location - Bangalore, India\n"
        "Requirements: Python, PyTorch, Scikit-learn, Machine Learning"
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res = run_fast_apply(text, threshold=2.0, artifact_dir=tmp_dir)
        assert res["status"] == "SUCCESS"
        assert res["pages"] == 1
        assert os.path.exists(res["pdf_path"])
        assert os.path.exists(res["application_md"])
        assert res["artifact_pdf"] is not None
        assert os.path.exists(res["artifact_pdf"])

        # Clean up generated test application directory
        app_dir = os.path.dirname(res["pdf_path"])
        if os.path.exists(app_dir):
            shutil.rmtree(app_dir, ignore_errors=True)
