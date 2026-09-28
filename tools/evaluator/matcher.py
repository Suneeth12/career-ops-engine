import math
import re
from collections import Counter
from typing import Dict, Any, List, Tuple, Set

STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't",
    "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "will", "shall", "role", "job", "candidate", "work",
    "team", "experience", "looking", "responsibilities", "requirements", "plus"
}

def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercased alphanumeric tokens, stripping punctuation."""
    if not text or not isinstance(text, str):
        return []
    tokens = re.findall(r'\b[A-Za-z0-9\+\#\.\_]{2,}\b', text.lower())
    return [t for t in tokens if t not in STOPWORDS and not t.isdigit()]

def get_ngrams(tokens: List[str], n: int = 2) -> List[str]:
    """Generate n-grams from a list of tokens."""
    return [" ".join(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]

class BM25ResumeMatcher:
    """
    High-speed, sub-millisecond ATS scoring engine implementing BM25 ranking
    and TF-IDF vector cosine similarity (inspired by Resume-Matcher & modern 2026 ATS algorithms).
    Runs with zero heavy ML dependencies for lightning fast pipeline execution.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def match(self, job_description: str, resume_text: str) -> Dict[str, Any]:
        jd_tokens = tokenize(job_description)
        resume_tokens = tokenize(resume_text)

        if not jd_tokens or not resume_tokens:
            return {
                "bm25_score": 0.0,
                "bm25_normalized_pct": 0.0,
                "cosine_similarity": 0.0,
                "cosine_similarity_pct": 0.0,
                "overall_ats_match_pct": 0.0,
                "matched_keywords": [],
                "missing_high_value_keywords": [],
                "top_jd_keywords": []
            }

        # N-grams (bi-grams) for multi-word technical concepts (e.g. 'machine learning', 'fastapi microservices')
        jd_bigrams = get_ngrams(jd_tokens, 2)
        resume_bigrams = get_ngrams(resume_tokens, 2)

        all_jd_features = jd_tokens + jd_bigrams
        all_res_features = set(resume_tokens + resume_bigrams)

        # 1. Frequency calculation for JD features & Resume counts (O(N) via Counter)
        jd_freq = Counter(all_jd_features)
        res_token_counts = Counter(resume_tokens)
        res_bigram_counts = Counter(resume_bigrams)

        # 2. BM25 calculation
        doc_len = len(resume_tokens)
        avg_doc_len = 350.0  # standard single-page resume word budget
        
        matched_features: List[Tuple[str, float]] = []
        missing_features: List[Tuple[str, float]] = []

        total_bm25 = 0.0
        max_possible_bm25 = 0.0

        for feat, count in jd_freq.items():
            # Simulated IDF based on feature length and specific tech keywords
            idf = math.log(1.0 + (100.0 / (count + 1.0)))
            tf_jd = (count * (self.k1 + 1)) / (count + self.k1)
            max_weight = idf * tf_jd
            max_possible_bm25 += max_weight

            if feat in all_res_features:
                res_count = res_token_counts[feat] if " " not in feat else res_bigram_counts[feat]
                tf_res = (res_count * (self.k1 + 1)) / (res_count + self.k1 * (1 - self.b + self.b * (doc_len / avg_doc_len)))
                weight = idf * tf_res
                total_bm25 += weight
                matched_features.append((feat, weight))
            else:
                missing_features.append((feat, max_weight))

        bm25_normalized = min(100.0, round((total_bm25 / max(0.1, max_possible_bm25)) * 100.0, 2))

        # 3. Fast Cosine Similarity on unigrams using Counter (O(N) vs O(N^2))
        c_jd = Counter(jd_tokens)
        c_res = res_token_counts
        all_vocab = set(c_jd.keys()).union(set(c_res.keys()))

        dot_prod = sum(c_jd[w] * c_res[w] for w in all_vocab)
        mag_jd = math.sqrt(sum(v * v for v in c_jd.values()))
        mag_res = math.sqrt(sum(v * v for v in c_res.values()))

        cosine_sim = (dot_prod / (mag_jd * mag_res)) if (mag_jd > 0 and mag_res > 0) else 0.0
        cosine_pct = round(cosine_sim * 100.0, 2)

        # Composite score combining BM25 keyword relevance (60%) and Vector Cosine Similarity (40%)
        overall_match = round(0.60 * bm25_normalized + 0.40 * cosine_pct, 2)

        # Sort features by weight
        matched_sorted = [f[0] for f in sorted(matched_features, key=lambda x: x[1], reverse=True)]
        missing_sorted = [f[0] for f in sorted(missing_features, key=lambda x: x[1], reverse=True)]
        top_jd = [f[0] for f in sorted(jd_freq.items(), key=lambda x: x[1], reverse=True)]

        return {
            "bm25_score": round(total_bm25, 2),
            "bm25_normalized_pct": bm25_normalized,
            "cosine_similarity": round(cosine_sim, 4),
            "cosine_similarity_pct": cosine_pct,
            "overall_ats_match_pct": overall_match,
            "matched_keywords": matched_sorted[:15],
            "missing_high_value_keywords": missing_sorted[:10],
            "top_jd_keywords": top_jd[:10]
        }
