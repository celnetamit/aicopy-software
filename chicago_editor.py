"""Chicago Manual of Style editing rules and corrections."""

import re
import os
import time
import json
import copy
import threading
from urllib.parse import quote
from typing import List, Tuple, Dict, Optional, Any, Callable

import requests


class ChicagoEditor:
    """Handles all Chicago Manual of Style corrections."""

    MISSING_PLACEHOLDER_RE = re.compile(r'\[[A-Za-z][A-Za-z ]* missing\]', flags=re.IGNORECASE)
    ONLINE_VALIDATION_ADMIN_CAP_DEFAULT = 150
    ONLINE_VALIDATION_MAX_REFERENCES = ONLINE_VALIDATION_ADMIN_CAP_DEFAULT
    ONLINE_VALIDATION_TIMEOUT_SECONDS = 5
    ONLINE_VALIDATION_CACHE_TTL_SECONDS = 6 * 60 * 60
    ONLINE_VALIDATION_CACHE_MAX_ENTRIES = 512
    SERPER_SEARCH_ENDPOINT = "https://google.serper.dev/search"
    SERPER_RESULTS_LIMIT = 5
    SERPER_MAX_TITLE_TERMS = 14
    SERPER_MAX_JOURNAL_TERMS = 6
    _SHARED_ONLINE_VALIDATION_CACHE: Dict[str, Dict[str, Any]] = {}
    _SHARED_ONLINE_VALIDATION_CACHE_LOCK = threading.Lock()
    _SHARED_ONLINE_LOOKUP_METRICS: Dict[str, int] = {
        "cache_hits": 0,
        "cache_misses": 0,
        "crossref_requests": 0,
        "openalex_requests": 0,
        "serper_requests": 0,
        "serper_cache_hits": 0,
    }
    _SHARED_ONLINE_LOOKUP_METRICS_UPDATED_AT: int = 0
    _SHARED_ONLINE_LOOKUP_METRICS_LOCK = threading.Lock()

    # American vs British spelling preferences (Chicago prefers American)
    PREFERRED_SPELLINGS = {
        'analyze': 'analyze', 'analyse': 'analyze',
        'center': 'center', 'centre': 'center',
        'color': 'color', 'colour': 'color',
        'defense': 'defense', 'defence': 'defense',
        'develop': 'develop', 'develope': 'develop',
        'favorite': 'favorite', 'favourite': 'favorite',
        'honor': 'honor', 'honour': 'honor',
        'humor': 'humor', 'humour': 'humor',
        'labor': 'labor', 'labour': 'labor',
        'neighbor': 'neighbor', 'neighbour': 'neighbor',
        'organize': 'organize', 'organise': 'organize',
        'realize': 'realize', 'realise': 'realize',
        'recognize': 'recognize', 'recognise': 'recognize',
        'travel': 'travel', 'travell': 'travel',
        'Canceled': 'Canceled', 'Cancelled': 'Canceled',
        ' installment': 'installment', 'instalment': 'installment',
        'fulfillment': 'fulfillment', 'fulfilment': 'fulfillment',
    }

    # Words that should always be capitalized
    PROPER_NOUNS = {
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        'january', 'february', 'march', 'april', 'may', 'june',
        'july', 'august', 'september', 'october', 'november', 'december',
        'spring', 'summer', 'fall', 'winter',
    }
    WEEKDAY_NAMES = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    MONTH_NAMES = ['january', 'february', 'march', 'april', 'may', 'june',
                   'july', 'august', 'september', 'october', 'november', 'december']
    AMBIGUOUS_MONTH_NAMES = {'march', 'may'}
    SUPERSCRIPT_MAP = str.maketrans({
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
        '+': '⁺', '-': '⁻'
    })
    NUMBER_WORDS = {
        'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
        'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18,
        'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40,
        'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90
    }
    MEASUREMENT_UNITS = {
        'mg', 'g', 'kg', 'ng', 'ug', 'mcg',
        'ml', 'mL', 'l', 'L',
        'mm', 'cm', 'm', 'km',
        'in', 'ft', 'yd', 'mi',
        'hz', 'khz', 'mhz', 'ghz',
        'v', 'kv', 'mv',
        'w', 'kw', 'mw',
        'a', 'ma',
        '°c', '°f', 'k',
    }
    JOURNAL_ABBREVIATIONS = {
        'academy': 'Acad',
        'american': 'Am',
        'analysis': 'Anal',
        'annual': 'Annu',
        'architectural': 'Archit',
        'architecture': 'Archit',
        'association': 'Assoc',
        'australian': 'Aust',
        'british': 'Br',
        'bulletin': 'Bull',
        'canadian': 'Can',
        'clinical': 'Clin',
        'communication': 'Commun',
        'comparative': 'Comp',
        'computing': 'Comput',
        'conference': 'Conf',
        'contemporary': 'Contemp',
        'design': 'Des',
        'development': 'Dev',
        'education': 'Educ',
        'engineering': 'Eng',
        'environment': 'Environ',
        'environmental': 'Environ',
        'european': 'Eur',
        'experimental': 'Exp',
        'global': 'Glob',
        'health': 'Health',
        'history': 'Hist',
        'indian': 'Indian',
        'information': 'Inf',
        'institute': 'Inst',
        'integrative': 'Integr',
        'international': 'Int',
        'journal': 'J',
        'management': 'Manag',
        'materials': 'Mater',
        'medicine': 'Med',
        'methods': 'Methods',
        'molecular': 'Mol',
        'modern': 'Mod',
        'national': 'Natl',
        'planning': 'Plan',
        'practice': 'Pract',
        'proceedings': 'Proc',
        'psychology': 'Psychol',
        'public': 'Public',
        'quarterly': 'Q',
        'research': 'Res',
        'review': 'Rev',
        'science': 'Sci',
        'sciences': 'Sci',
        'social': 'Soc',
        'society': 'Soc',
        'studies': 'Stud',
        'study': 'Study',
        'sustainability': 'Sustain',
        'sustainable': 'Sustain',
        'systems': 'Syst',
        'technology': 'Technol',
        'theory': 'Theory',
        'urban': 'Urban',
        'university': 'Univ',
        'world': 'World',
    }
    JOURNAL_STOPWORDS = {'of', 'the', 'and', 'for', 'in', 'on', 'to', 'a', 'an'}
    TITLE_ACRONYMS = {
        'AI', 'AR', 'BIM', 'DNA', 'EU', 'GIS', 'HIV', 'IoT', 'LCA', 'ML', 'NLP',
        'RNA', 'UK', 'UN', 'USA', 'VR'
    }
    TITLE_PROPER_WORDS = {
        'africa', 'american', 'asia', 'australia', 'britain', 'british', 'china',
        'europe', 'european', 'india', 'indian', 'latin', 'london', 'new', 'york',
        'usa', 'united'
    }
    MEDICAL_TERMS = {
        'analgesia', 'antibiotic', 'biopsy', 'cardiovascular', 'comorbidity', 'cytokine', 'diagnosis',
        'differential diagnosis', 'dosage', 'etiology', 'hematology', 'histopathology', 'hypertension',
        'immunology', 'inflammation', 'intravenous', 'metastasis', 'morbidity', 'mortality', 'myocardial',
        'neurology', 'oncology', 'pathology', 'pharmacokinetics', 'pharmacology', 'physiology', 'prognosis',
        'radiology', 'randomized controlled trial', 'sepsis', 'serology', 'therapeutic', 'thrombosis',
        'toxicology', 'vaccine', 'viral load', 'in vitro', 'in vivo'
    }
    ENGINEERING_TERMS = {
        'algorithm', 'bandwidth', 'cad', 'cfd', 'compressive strength', 'control system', 'debugging',
        'finite element analysis', 'firmware', 'load bearing', 'mach number', 'manufacturability',
        'mechanical tolerance', 'microcontroller', 'modulus of elasticity', 'optimization', 'pid controller',
        'powertrain', 'prototype', 'quality assurance', 'reinforced concrete', 'requirements engineering',
        'signal processing', 'software architecture', 'specification', 'stress analysis', 'thermodynamics',
        'throughput', 'torque', 'validation', 'verification', 'voltage', 'weldability'
    }
    LEGAL_TERMS = {
        'affidavit', 'arbitration', 'burden of proof', 'case law', 'cause of action', 'civil procedure',
        'common law', 'contractual', 'cross-examination', 'damages', 'deposition', 'equity', 'estoppel',
        'habeas corpus', 'indemnity', 'injunction', 'jurisdiction', 'litigation', 'mens rea', 'actus reus',
        'negligence', 'plaintiff', 'precedent', 'prima facie', 'pro bono', 'res judicata', 'statutory',
        'sub judice', 'testimony', 'tort', 'ultra vires', 'verdict', 'writ'
    }
    FOREIGN_TERMS = {
        'et al', 'in vitro', 'in vivo', 'ad hoc', 'de facto', 'prima facie', 'inter alia',
        'per se', 'a priori', 'post hoc', 'vice versa', 'status quo', 'pro bono',
        'habeas corpus', 'mens rea', 'actus reus', 'sub judice', 'ultra vires',
        'mutatis mutandis', 'sui generis', 'ipso facto', 'ibid', 'cf'
    }
    FOREIGN_TERMS_ROMAN = {
        'et al', 'in vitro', 'in vivo', 'ad hoc', 'de facto', 'prima facie',
        'per se', 'a priori', 'post hoc', 'vice versa', 'status quo', 'pro bono',
        'ibid', 'cf'
    }
    FOREIGN_TERMS_ITALIC = FOREIGN_TERMS - FOREIGN_TERMS_ROMAN
    TITLE_SMALL_WORDS = {
        'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'if', 'in',
        'of', 'on', 'or', 'per', 'the', 'to', 'via', 'vs'
    }
    JOURNAL_PROFILES = {
        'vancouver_nlm': {
            'label': 'Vancouver (NLM, no initial periods)',
            'initials_with_periods': False,
            'title_case': 'sentence',
            'journal_abbrev': 'nlm',
        },
        'vancouver_periods': {
            'label': 'Vancouver (Initial periods)',
            'initials_with_periods': True,
            'title_case': 'sentence',
            'journal_abbrev': 'nlm',
        },
        'vancouver_full': {
            'label': 'Vancouver (Full Journal Names)',
            'initials_with_periods': False,
            'title_case': 'sentence',
            'journal_abbrev': 'full',
        },
        'vancouver_periods_full': {
            'label': 'Vancouver (Initial Periods + Full Journal Names)',
            'initials_with_periods': True,
            'title_case': 'sentence',
            'journal_abbrev': 'full',
        },
        'vancouver_titlecase_nlm': {
            'label': 'Vancouver (Title Case Titles + NLM Journal Abbrev.)',
            'initials_with_periods': False,
            'title_case': 'title',
            'journal_abbrev': 'nlm',
        },
    }
    JOURNAL_PROFILE_ALIASES = {
        'vancouver': 'vancouver_periods',
        'vancouver_nlm': 'vancouver_nlm',
        'vancouver_periods': 'vancouver_periods',
        'vancouver_full': 'vancouver_full',
        'vancouver_full_journal': 'vancouver_full',
        'vancouver_periods_full': 'vancouver_periods_full',
        'vancouver_periods_full_journal': 'vancouver_periods_full',
        'vancouver_titlecase_nlm': 'vancouver_titlecase_nlm',
        'vancouver_title_case_nlm': 'vancouver_titlecase_nlm',
        'vancouver_titlecase': 'vancouver_titlecase_nlm',
    }

    def __init__(self):
        self.corrections: List[Dict] = []
        self.last_domain_profile: str = "general"
        self.last_domain_scores: Dict[str, int] = {"medical": 0, "engineering": 0, "law": 0}
        self.last_protected_domain_terms: int = 0
        self.last_custom_terms_count: int = 0
        self._online_validation_cache = self.__class__._SHARED_ONLINE_VALIDATION_CACHE
        self._online_validation_cache_lock = self.__class__._SHARED_ONLINE_VALIDATION_CACHE_LOCK
        self._online_lookup_metrics_lock = self.__class__._SHARED_ONLINE_LOOKUP_METRICS_LOCK
        self._online_lookup_metrics: Dict[str, int] = {}

    @staticmethod
    def _default_online_lookup_metrics() -> Dict[str, int]:
        """Default zeroed lookup metrics schema."""
        return {
            "cache_hits": 0,
            "cache_misses": 0,
            "crossref_requests": 0,
            "openalex_requests": 0,
            "serper_requests": 0,
            "serper_cache_hits": 0,
        }

    def _reset_online_lookup_metrics(self):
        """Reset per-run counters for external lookup observability."""
        self._online_lookup_metrics = self._default_online_lookup_metrics()

    def _increment_online_lookup_metric(self, key: str, value: int = 1):
        """Increment one lookup metric counter."""
        if not key:
            return
        current = int(self._online_lookup_metrics.get(key, 0) or 0)
        self._online_lookup_metrics[key] = current + int(value)

    def _publish_online_lookup_metrics(self):
        """Publish this run's lookup metrics to process-shared diagnostics state."""
        with self._online_lookup_metrics_lock:
            for key, value in (self._online_lookup_metrics or {}).items():
                current = int(self.__class__._SHARED_ONLINE_LOOKUP_METRICS.get(key, 0) or 0)
                self.__class__._SHARED_ONLINE_LOOKUP_METRICS[key] = current + int(value or 0)
            self.__class__._SHARED_ONLINE_LOOKUP_METRICS_UPDATED_AT = int(time.time())

    def get_online_validation_diagnostics(self) -> Dict[str, Any]:
        """Return safe process-level diagnostics for online reference validation."""
        now = time.time()
        with self._online_validation_cache_lock:
            cache_items = list(self._online_validation_cache.items())
        with self._online_lookup_metrics_lock:
            shared_lookup_metrics = dict(self.__class__._SHARED_ONLINE_LOOKUP_METRICS)
            shared_lookup_metrics_updated_at = int(self.__class__._SHARED_ONLINE_LOOKUP_METRICS_UPDATED_AT or 0)
        namespaces: Dict[str, int] = {}
        active_entries = 0
        expired_entries = 0
        for key, payload in cache_items:
            namespace = str(key or "").split(":", 1)[0] or "unknown"
            namespaces[namespace] = int(namespaces.get(namespace, 0)) + 1
            expires_at = float((payload or {}).get("expires_at") or 0)
            if expires_at > now:
                active_entries += 1
            else:
                expired_entries += 1
        return {
            "serper_configured": bool(self._get_serper_api_key()),
            "serper_endpoint": self.SERPER_SEARCH_ENDPOINT,
            "limits": {
                "max_references": self.ONLINE_VALIDATION_ADMIN_CAP_DEFAULT,
                "dynamic_limit_policy": "min(total_detected_references, admin_cap)",
                "timeout_seconds": self.ONLINE_VALIDATION_TIMEOUT_SECONDS,
                "serper_results_limit": self.SERPER_RESULTS_LIMIT,
                "serper_max_title_terms": self.SERPER_MAX_TITLE_TERMS,
                "serper_max_journal_terms": self.SERPER_MAX_JOURNAL_TERMS,
            },
            "cache": {
                "entries_total": len(cache_items),
                "entries_active": active_entries,
                "entries_expired": expired_entries,
                "max_entries": self.ONLINE_VALIDATION_CACHE_MAX_ENTRIES,
                "ttl_seconds": self.ONLINE_VALIDATION_CACHE_TTL_SECONDS,
                "namespaces": namespaces,
            },
            "lookup_metrics": shared_lookup_metrics,
            "lookup_metrics_updated_at": shared_lookup_metrics_updated_at,
        }

    def reset_online_validation_cache(self) -> int:
        """Clear shared online validation cache and return removed entry count."""
        with self._online_validation_cache_lock:
            removed = len(self._online_validation_cache)
            self._online_validation_cache.clear()
        with self._online_lookup_metrics_lock:
            self.__class__._SHARED_ONLINE_LOOKUP_METRICS = self._default_online_lookup_metrics()
            self.__class__._SHARED_ONLINE_LOOKUP_METRICS_UPDATED_AT = int(time.time())
        return removed

    def correct_all(self, text: str, options: Dict) -> str:
        """Apply all selected corrections."""
        self.corrections = []
        protected_text, protected_tokens = self._protect_invariant_tokens(text, options)
        result = protected_text

        if options.get('spelling', True):
            result = self.correct_spelling(result)

        if options.get('sentence_case', True):
            result = self.correct_sentence_case(result)

        if options.get('punctuation', True):
            result = self.correct_punctuation(result)

        if options.get('chicago_style', True):
            result = self.apply_chicago_style(result, options)

        return self._restore_invariant_tokens(result, protected_tokens)

    def postprocess_ai_first_copyedit(self, text: str, options: Optional[Dict] = None) -> str:
        """Apply only structure-safe normalization after AI-first language editing."""
        safe_options = options if isinstance(options, dict) else {}
        protected_text, protected_tokens = self._protect_invariant_tokens(text, safe_options)
        result = protected_text

        if safe_options.get('punctuation', True):
            result = self.correct_punctuation(result)

        if safe_options.get('chicago_style', True):
            result = self.normalize_word_number_markers(result)
            result = self.collapse_mixed_parenthetical_citations(result)
            result = self.normalize_numeric_citations(result)
            result = self.merge_adjacent_numeric_citations(result)
            result = self.format_author_markers_as_superscript(result)
            result = self.normalize_author_line_name_markers(result)
            result = self.normalize_keywords_line(result)
            result = self.apply_cmos_profile_rule_pack(result, safe_options)
            result = self.format_references_vancouver_numbered(result, safe_options)

        return self._restore_invariant_tokens(result, protected_tokens)

    def _normalize_domain_profile(self, options: Optional[Dict]) -> str:
        """Resolve requested domain profile."""
        if not isinstance(options, dict):
            return "auto"
        profile = str(options.get("domain_profile", "auto")).strip().lower()
        if profile in ("auto", "general", "medical", "engineering", "law"):
            return profile
        return "auto"

    def _select_domain_terms(self, text: str, options: Optional[Dict]) -> set:
        """Pick a domain dictionary (or none) based on options and detected content."""
        profile = self._normalize_domain_profile(options)
        catalog = {
            "medical": self.MEDICAL_TERMS,
            "engineering": self.ENGINEERING_TERMS,
            "law": self.LEGAL_TERMS,
        }

        lower_text = (text or "").lower()
        scores: Dict[str, int] = {}
        for key, terms in catalog.items():
            hit = 0
            for term in terms:
                pattern = r'(?<!\w)' + re.escape(term.lower()) + r'(?!\w)'
                if re.search(pattern, lower_text):
                    hit += 1
            scores[key] = hit
        self.last_domain_scores = scores

        if profile in catalog:
            self.last_domain_profile = profile
            return set(catalog[profile])
        if profile == "general":
            self.last_domain_profile = "general"
            return set()

        best_profile = max(scores, key=scores.get) if scores else "general"
        if scores.get(best_profile, 0) >= 2:
            self.last_domain_profile = best_profile
            return set(catalog[best_profile])

        self.last_domain_profile = "general"
        return set()

    def _extract_custom_terms(self, options: Optional[Dict]) -> set:
        """Extract validated custom glossary terms from options payload."""
        if not isinstance(options, dict):
            self.last_custom_terms_count = 0
            return set()

        raw = options.get("custom_terms", [])
        terms: set = set()

        if isinstance(raw, str):
            candidates = re.split(r'[\n,;]+', raw)
        elif isinstance(raw, list):
            candidates = raw
        else:
            candidates = []

        for candidate in candidates:
            value = str(candidate).strip()
            if len(value) < 2 or len(value) > 80:
                continue
            terms.add(value)
            if len(terms) >= 500:
                break

        self.last_custom_terms_count = len(terms)
        return terms

    def get_journal_profile_catalog(self) -> List[Dict[str, str]]:
        """Return available journal profile options for UI/docs."""
        out: List[Dict[str, str]] = []
        for profile_id, profile in self.JOURNAL_PROFILES.items():
            out.append({
                "id": profile_id,
                "label": str(profile.get("label", profile_id)),
            })
        return out

    def resolve_journal_profile(self, options: Optional[Dict]) -> Dict[str, Any]:
        """Resolve selected journal profile, with backward-compatible aliases."""
        requested = ""
        if isinstance(options, dict):
            requested = str(
                options.get("journal_profile") or options.get("reference_profile") or "vancouver_nlm"
            ).strip().lower()

        profile_id = self.JOURNAL_PROFILE_ALIASES.get(requested, requested)
        if profile_id not in self.JOURNAL_PROFILES:
            profile_id = "vancouver_nlm"

        resolved = dict(self.JOURNAL_PROFILES[profile_id])
        resolved["id"] = profile_id
        return resolved

    def _normalize_cmos_profile(self, options: Optional[Dict]) -> str:
        """Resolve CMOS expansion profile for Phase 2 rule packs."""
        if not isinstance(options, dict):
            return "core"
        value = str(options.get("cmos_profile", "core") or "core").strip().lower()
        if value in ("core", "strict", "journal_custom"):
            return value
        return "core"

    def _protect_invariant_tokens(self, text: str, options: Optional[Dict] = None) -> Tuple[str, Dict[str, str]]:
        """Protect tokens that must remain byte-for-byte intact during editing."""
        replacements: Dict[str, str] = {}
        counter = 0
        masked = text
        domain_terms = self._select_domain_terms(text, options)
        custom_terms = self._extract_custom_terms(options)
        protected_terms = {
            term for term in (set(domain_terms) | set(custom_terms))
            if term.lower() not in self.FOREIGN_TERMS
        }
        self.last_protected_domain_terms = 0

        patterns = [
            # Full URLs.
            re.compile(r'(?i)\b(?:https?|ftp)://[^\s<>"\']+'),
            # Common bare web URLs.
            re.compile(r'(?i)\bwww\.[^\s<>"\']+'),
            # DOI with explicit label.
            re.compile(r'(?i)\bdoi:\s*10\.\d{4,9}/[^\s<>"\']+'),
            # Bare DOI token.
            re.compile(r'(?i)\b10\.\d{4,9}/[^\s<>"\']+'),
            # Emails.
            re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
        ]

        def make_replacer():
            nonlocal counter

            def repl(match):
                nonlocal counter
                token = match.group(0)
                trailing = ""
                while token and token[-1] in ".,;:!?":
                    trailing = token[-1] + trailing
                    token = token[:-1]

                placeholder = f"__INV_TOKEN_{counter}__"
                counter += 1
                replacements[placeholder] = token
                return placeholder + trailing

            return repl

        for pattern in patterns:
            masked = pattern.sub(make_replacer(), masked)

        if protected_terms:
            sorted_terms = sorted(protected_terms, key=len, reverse=True)
            for term in sorted_terms:
                pattern = re.compile(r'(?i)(?<!\w)' + re.escape(term) + r'(?!\w)')
                before = masked
                masked = pattern.sub(make_replacer(), masked)
                if masked != before:
                    self.last_protected_domain_terms += 1

        return masked, replacements

    def _restore_invariant_tokens(self, text: str, replacements: Dict[str, str]) -> str:
        """Restore protected tokens after normalization."""
        result = text
        for placeholder, original in replacements.items():
            result = result.replace(placeholder, original)
        return result

    def correct_spelling(self, text: str) -> str:
        """Fix common spelling errors."""
        words = re.findall(r'\b\w+\b', text)
        result = text

        for wrong, correct in self.PREFERRED_SPELLINGS.items():
            pattern = re.compile(r'\b' + re.escape(wrong) + r'\b', re.IGNORECASE)
            result = pattern.sub(correct, result)

        # Common homophone errors
        homophones = [
            (r'\bit\'s\b', "it's", r"it's", "it is"),
            (r'\bits\b', "its", r"its", "possessive"),
            (r'\btheir\b', "their", r"their", "possessive"),
            (r'\bthere\b', "there", r"there", "location"),
            (r'\bthey\'re\b', "they're", r"they're", "they are"),
            (r'\byou\'re\b', "you're", r"you're", "you are"),
            (r'\byour\b', "your", r"your", "possessive"),
            (r'\bloose\b', "lose", r"loose", "not tight"),
            (r'\blosing\b', "losing", r"losing", "verb"),
            (r'\brecieve\b', "receive", r"recieve", ""),
            (r'\boccured\b', "occurred", r"occured", ""),
            (r'\bseperate\b', "separate", r"seperate", ""),
            (r'\bdefinately\b', "definitely", r"definately", ""),
            (r'\buntill\b', "until", r"untill", ""),
            (r'\barguement\b', "argument", r"arguement", ""),
            (r'\boccurrance\b', "occurrence", r"occurrance", ""),
            (r'\bpersistant\b', "persistent", r"persistant", ""),
            (r'\brecommend\b', "recommend", r"recomend", ""),
            (r'\bembarrass\b', "embarrass", r"embarass", ""),
            (r'\brefrences\b', "references", r"refrences", ""),
            (r'\brefrence\b', "reference", r"refrence", ""),
            (r'\bgrahmer\b', "grammar", r"grahmer", ""),
            (r'\bgrammer\b', "grammar", r"grammer", ""),
            (r'\bteh\b', "the", r"teh", ""),
        ]

        for pattern_str, replacement, original, note in homophones:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            result = pattern.sub(replacement, result)

        return result

    def correct_sentence_case(self, text: str) -> str:
        """Fix capitalization issues."""
        result = text

        # Fix first letter of document
        if result and result[0].islower():
            result = result[0].upper() + result[1:]

        # Fix sentence beginnings (after . ! ?)
        sentence_end = r'([.!?]\s+)'
        matches = list(re.finditer(sentence_end, result))

        for match in reversed(matches):
            gap = match.end()
            if gap < len(result):
                next_char = result[gap]
                if next_char.islower():
                    result = result[:gap] + next_char.upper() + result[gap+1:]

        # Capitalize weekdays and unambiguous month names. Ambiguous month
        # words like "may" and "march" need context so verbs/modal auxiliaries
        # are not promoted to proper nouns in body text.
        for day in self.WEEKDAY_NAMES:
            result = re.sub(r'\b' + day + r'\b', day.capitalize(), result, flags=re.IGNORECASE)

        for month in self.MONTH_NAMES:
            if month in self.AMBIGUOUS_MONTH_NAMES:
                continue
            result = re.sub(r'\b' + month + r'\b', month.capitalize(), result, flags=re.IGNORECASE)

        result = self._capitalize_ambiguous_month_references(result)

        return result

    def _capitalize_ambiguous_month_references(self, text: str) -> str:
        """Capitalize ambiguous month names only in date-like contexts."""
        result = text
        ambiguous = '|'.join(sorted(self.AMBIGUOUS_MONTH_NAMES))
        prepositions = (
            'in', 'on', 'by', 'during', 'through', 'throughout', 'from', 'until',
            'before', 'after', 'since', 'around', 'late', 'early', 'mid',
            'next', 'last', 'this', 'each', 'every'
        )
        preposition_pattern = '|'.join(prepositions)

        result = re.sub(
            rf'\b((?:{preposition_pattern})\s+)(?P<month>{ambiguous})\b',
            lambda match: match.group(1) + match.group('month').capitalize(),
            result,
            flags=re.IGNORECASE,
        )
        result = re.sub(
            rf'\b(?P<month>{ambiguous})(?=(?:\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,\s*\d{{4}})?)|\s+\d{{4}}\b)',
            lambda match: match.group('month').capitalize(),
            result,
            flags=re.IGNORECASE,
        )
        result = re.sub(
            rf'(\b\d{{1,2}}(?:st|nd|rd|th)?\s+of\s+)(?P<month>{ambiguous})\b',
            lambda match: match.group(1) + match.group('month').capitalize(),
            result,
            flags=re.IGNORECASE,
        )

        return result

    def correct_punctuation(self, text: str) -> str:
        """Refine punctuation per Chicago style."""
        result = text

        # Fix double spaces
        result = re.sub(r'  +', ' ', result)

        # Fix spacing around punctuation
        result = re.sub(r'\s+([.,;:!?])', r'\1', result)
        # Add missing spaces after punctuation that should typically be followed by a space.
        result = re.sub(r'([,;:!?])(?!\s)(?=[^\s])', r'\1 ', result)
        # Add missing space after sentence-ending period when followed by uppercase.
        result = re.sub(r'(?<=[a-z0-9])\.(?=[A-Z])', '. ', result)

        # Ensure em-dash has no spaces (Chicago style)
        result = re.sub(r'\s*--\s*', '—', result)

        # Ensure proper ellipsis (three dots, not ..., . . ., etc.)
        result = re.sub(r'\.{3,}', '...', result)
        result = re.sub(r'(?<!\.)\.(?!\.)\s*\.\s*(?!\.)', '...', result)

        # Fix quotation marks to straight quotes (simplified)
        result = re.sub(r'[""]', '"', result)
        result = re.sub(r"['']", "'", result)

        return result

    def apply_chicago_style(self, text: str, options: Optional[Dict] = None) -> str:
        """Apply broader Chicago Manual of Style formatting."""
        result = text

        # Normalize word-number markers before citation/author formatting.
        result = self.normalize_word_number_markers(result)
        # Collapse mixed author-year + bracket citation forms into numeric-only citation blocks.
        result = self.collapse_mixed_parenthetical_citations(result)
        # Keep numeric citation format stable.
        result = self.normalize_numeric_citations(result)
        # Merge adjacent bracket citations like [9] [19] -> [9, 19].
        result = self.merge_adjacent_numeric_citations(result)
        # Use superscript for author affiliation/index markers.
        result = self.format_author_markers_as_superscript(result)
        # Normalize author-line names/titles and place affiliation marker after author name.
        result = self.normalize_author_line_name_markers(result)
        # Keep common foreign terms in lowercase form.
        result = self.normalize_foreign_terms(result)
        # Prefer scientific styling for percentages.
        result = self.normalize_scientific_percentages(result)
        # Prefer numerals with abbreviated scientific measurements.
        result = self.normalize_measurement_numerals(result)
        # Ensure keyword lines use sentence case per item.
        result = self.normalize_keywords_line(result)
        # Phase 2 CMOS expansion layer (profile-based rule pack).
        result = self.apply_cmos_profile_rule_pack(result, options)
        # Enforce Vancouver numbering so citations and references follow first appearance.
        result = self.format_references_vancouver_numbered(result, options or {})

        return result

    def apply_cmos_profile_rule_pack(self, text: str, options: Optional[Dict] = None) -> str:
        """Apply Phase 2 CMOS profile-specific rule packs."""
        result = str(text or "")
        profile = self._normalize_cmos_profile(options)
        if profile == "core":
            return result

        # Shared safe pack used by strict/journal_custom.
        result = self._rule_tulsi_specific_vs_generic(result)
        result = re.sub(r'(?i)\bet\s+al\.\s*,', 'et al.', result)
        result = re.sub(r'(?i)\be\.g\.(?!,)', 'e.g.,', result)
        result = re.sub(r'(?i)\bi\.e\.(?!,)', 'i.e.,', result)

        if profile == "strict":
            # Oxford comma for simple serial lists ("A, B and C" -> "A, B, and C").
            result = re.sub(
                r'\b([A-Z][a-z]+,\s+[A-Z][a-z]+)\s+and\s+([A-Z][a-z]+)\b',
                r'\1, and \2',
                result,
            )
            # Tighten common abbreviation spacing.
            result = re.sub(r'(?i)\b(fig|eq|ref)\.\s+(\d)', lambda m: f"{m.group(1).capitalize()}. {m.group(2)}", result)
            # Strict content-level CMOS normalization for body prose.
            result = self._strict_cmos_content_pack(result)

        if profile == "journal_custom":
            # Journal-custom keeps title/sentence tuning conservative but enforces DOI label form.
            result = re.sub(r'(?i)\bdoi\s*:\s*', 'doi: ', result)

        return result

    def _strict_cmos_content_pack(self, text: str) -> str:
        """Apply safe, body-text CMOS normalizations for strict mode."""
        result = str(text or "")
        result = self._apply_serial_comma_general(result)
        result = self._normalize_vs_abbreviation(result)
        result = self._normalize_latin_abbreviations(result)
        result = self._normalize_time_abbreviations(result)
        return result

    def _apply_serial_comma_general(self, text: str) -> str:
        """Insert serial comma in common lower/upper-case three-item lists."""
        return re.sub(
            r'\b([A-Za-z][A-Za-z-]*,\s+[A-Za-z][A-Za-z-]*)\s+and\s+([A-Za-z][A-Za-z-]*)\b',
            r'\1, and \2',
            text,
        )

    def _normalize_vs_abbreviation(self, text: str) -> str:
        """CMOS preference: 'vs.' instead of bare 'vs' in running text."""
        return re.sub(r'(?i)\bvs\b(?!\.)', 'vs.', text)

    def _normalize_latin_abbreviations(self, text: str) -> str:
        """Ensure CMOS punctuation/spacing for common Latin abbreviations."""
        result = str(text or "")
        # Preserve standard "etc." and only add a terminal period when bare "etc" appears.
        result = re.sub(r'(?i)\betc(?!\.)(?=[\s;:)\].]|$)', 'etc.', result)
        return result

    def _normalize_time_abbreviations(self, text: str) -> str:
        """Use lowercase am/pm with periods in prose."""
        result = str(text or "")
        result = re.sub(r'\b([0-9]{1,2})\s*AM\b', r'\1 a.m.', result)
        result = re.sub(r'\b([0-9]{1,2})\s*PM\b', r'\1 p.m.', result)
        result = re.sub(r'\b([0-9]{1,2})\s*am\b', r'\1 a.m.', result)
        result = re.sub(r'\b([0-9]{1,2})\s*pm\b', r'\1 p.m.', result)
        return result

    def _rule_tulsi_specific_vs_generic(self, text: str) -> str:
        """Use Tulsi for specific/cultural plant naming; tulsi for generic mentions."""
        result = str(text or "")
        result = re.sub(r'\b[Tt]ulsi\s+plant\b', 'Tulsi plant', result)
        result = re.sub(r'\b(?:the|a)\s+Tulsi\b', lambda m: m.group(0).replace('Tulsi', 'tulsi'), result)
        return result

    def _word_to_number(self, raw: str) -> int:
        """Convert a small English number phrase (0-99) to integer."""
        token = raw.strip().lower().replace('-', ' ')
        if token in self.NUMBER_WORDS:
            return self.NUMBER_WORDS[token]

        parts = [p for p in token.split() if p]
        if len(parts) == 2 and parts[0] in self.NUMBER_WORDS and parts[1] in self.NUMBER_WORDS:
            return self.NUMBER_WORDS[parts[0]] + self.NUMBER_WORDS[parts[1]]

        raise ValueError(f"Unsupported number word: {raw}")

    def normalize_word_number_markers(self, text: str) -> str:
        """Convert citation/author number words (e.g., [nine], one.) to digits."""
        word_pattern = (
            r'(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|'
            r'thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|'
            r'thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|'
            r'four|five|six|seven|eight|nine))?'
        )

        # [nine] -> [9]
        def citation_word_repl(match):
            raw = match.group(1)
            try:
                return f'[{self._word_to_number(raw)}]'
            except ValueError:
                return match.group(0)

        text = re.sub(r'\[\s*(' + word_pattern + r')\s*\]', citation_word_repl, text, flags=re.IGNORECASE)

        # "one. Dr. ..." -> "1. Dr. ..."
        def author_marker_repl(match):
            raw = match.group(1)
            try:
                return f'{self._word_to_number(raw)}. '
            except ValueError:
                return match.group(0)

        text = re.sub(
            r'\b(' + word_pattern + r')\s*\.\s*(?=(?:Dr|Ar|Prof|Professor|Mr|Mrs|Ms)\.?\s)',
            author_marker_repl,
            text,
            flags=re.IGNORECASE
        )

        # Leading affiliation marker lists: "one, three, Assistant..." -> "1,3, Assistant..."
        def line_start_list_repl(match):
            markers = match.group(1)
            converted = []
            for part in re.split(r'\s*,\s*', markers):
                try:
                    converted.append(str(self._word_to_number(part)))
                except ValueError:
                    return match.group(0)
            return ','.join(converted) + ', '

        text = re.sub(
            r'^\s*((?:' + word_pattern + r')(?:\s*,\s*' + word_pattern + r')+)\s*,\s+',
            line_start_list_repl,
            text,
            flags=re.IGNORECASE | re.MULTILINE
        )

        return text

    def normalize_numeric_citations(self, text: str) -> str:
        """Normalize citation blocks like [1] or [1,2,3]."""
        def repl(match):
            nums = [n.strip() for n in match.group(1).split(',') if n.strip()]
            return '[' + ', '.join(nums) + ']'

        return re.sub(r'\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]', repl, text)

    def collapse_mixed_parenthetical_citations(self, text: str) -> str:
        """Convert mixed forms like '(Author, 1995 [9]) [19]' into '[9, 19]'."""
        citation_pattern = re.compile(
            r'\(([^()]*\[\s*\d+(?:\s*,\s*\d+)*\s*\][^()]*)\)\s*(\[\s*\d+(?:\s*,\s*\d+)*\s*\])?',
            flags=re.MULTILINE
        )

        def parse_nums(fragment: str) -> List[str]:
            values: List[str] = []
            for grp in re.findall(r'\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]', fragment):
                for part in grp.split(','):
                    number = part.strip()
                    if number and number not in values:
                        values.append(number)
            return values

        def repl(match):
            inside = match.group(1) or ''
            trailing = match.group(2) or ''
            nums = parse_nums(inside + ' ' + trailing)
            if not nums:
                return match.group(0)
            return '[' + ', '.join(nums) + ']'

        return citation_pattern.sub(repl, text)

    def merge_adjacent_numeric_citations(self, text: str) -> str:
        """Merge adjacent numeric citation blocks into one normalized citation list."""
        pattern = re.compile(
            r'\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]\s*\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]'
        )

        def repl(match):
            left = [n.strip() for n in match.group(1).split(',') if n.strip()]
            right = [n.strip() for n in match.group(2).split(',') if n.strip()]
            merged: List[str] = []
            for n in left + right:
                if n not in merged:
                    merged.append(n)
            return '[' + ', '.join(merged) + ']'

        previous = None
        current = text
        while previous != current:
            previous = current
            current = pattern.sub(repl, current)
        return current

    def format_author_markers_as_superscript(self, text: str) -> str:
        """Convert author affiliation markers like `1. Dr.` to superscript digits."""
        def repl(match):
            number = match.group(1).translate(self.SUPERSCRIPT_MAP)
            return f'{number} '

        return re.sub(
            r'\b(\d{1,2})\s*\.\s*(?=(?:Dr|Ar|Prof|Professor|Mr|Mrs|Ms)\.?\s)',
            repl,
            text
        )

    def normalize_author_line_name_markers(self, text: str) -> str:
        """Normalize author front-matter lines to 'Name²*' style and remove titles."""
        title_re = re.compile(r'^(?:(?:Ar|Dr|Prof|Professor|Mr|Mrs|Ms)\.?\s+)+', flags=re.IGNORECASE)
        leading_marker_re = re.compile(r'^\s*([⁰¹²³⁴⁵⁶⁷⁸⁹]+|\d{1,2})(?:\s*[.)])?\s*')
        trailing_marker_re = re.compile(r'\s*([⁰¹²³⁴⁵⁶⁷⁸⁹]+|\d{1,2})\s*$')

        def to_superscript(raw: str) -> str:
            token = raw.strip()
            if not token:
                return ''
            if re.fullmatch(r'[⁰¹²³⁴⁵⁶⁷⁸⁹]+', token):
                return token
            if token.isdigit():
                return token.translate(self.SUPERSCRIPT_MAP)
            return token

        def normalize_segment(segment: str) -> str:
            src = segment.strip()
            if not src:
                return src

            marker = ''
            stars = ''

            lead = leading_marker_re.match(src)
            if lead:
                marker = to_superscript(lead.group(1))
                src = src[lead.end():].strip()

            src = title_re.sub('', src).strip()

            star_match = re.search(r'(\*+)\s*$', src)
            if star_match:
                stars = star_match.group(1)
                src = src[:star_match.start()].strip()

            trail = trailing_marker_re.search(src)
            if trail:
                if not marker:
                    marker = to_superscript(trail.group(1))
                src = src[:trail.start()].strip()

            src = re.sub(r'\s+', ' ', src).strip(' ,;')
            if not src:
                return segment.strip()

            return f'{src}{marker}{stars}'

        output_lines: List[str] = []
        for line in text.split('\n'):
            stripped = line.strip()
            if not stripped:
                output_lines.append(line)
                continue

            # Conservative trigger for author-name lines.
            if (
                ',' in stripped and
                re.search(r'\b(?:Ar|Dr|Prof|Professor|Mr|Mrs|Ms)\.?\b', stripped, flags=re.IGNORECASE)
            ):
                parts = [part.strip() for part in line.split(',')]
                normalized_parts = [normalize_segment(part) for part in parts]
                output_lines.append(', '.join(normalized_parts))
                continue

            output_lines.append(line)

        return '\n'.join(output_lines)

    def normalize_keywords_line(self, text: str) -> str:
        """Normalize `Keyword:` / `Keywords:` label while preserving item casing."""

        output_lines = []
        for line in text.split('\n'):
            match = re.match(r'^(\s*keywords?\s*:\s*)(.*)$', line, flags=re.IGNORECASE)
            if not match:
                output_lines.append(line)
                continue

            raw_prefix = str(match.group(1) or "")
            prefix = "Keywords: " if re.search(r'keywords', raw_prefix, flags=re.IGNORECASE) else "Keyword: "
            # Keep author-provided technical/brand casing in each keyword item.
            items = [part.strip() for part in match.group(2).split(',')]
            output_lines.append(prefix + ', '.join(items))

        return '\n'.join(output_lines)

    def normalize_foreign_terms(self, text: str) -> str:
        """Normalize known non-English scholarly terms to lowercase."""
        result = text
        for term in sorted(self.FOREIGN_TERMS, key=len, reverse=True):
            pattern = re.compile(r'(?i)(?<!\w)' + re.escape(term) + r'(?!\w)')
            result = pattern.sub(term.lower(), result)
        return result

    def get_foreign_term_style_catalog(self) -> Dict[str, List[str]]:
        """Return foreign-term categories for Chicago-style rendering decisions."""
        return {
            "roman": sorted(self.FOREIGN_TERMS_ROMAN, key=len, reverse=True),
            "italic": sorted(self.FOREIGN_TERMS_ITALIC, key=len, reverse=True),
        }

    def normalize_scientific_percentages(self, text: str) -> str:
        """Convert scientific percentage expressions to numeral + % form."""
        word_pattern = (
            r'(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|'
            r'thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|'
            r'thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|'
            r'four|five|six|seven|eight|nine))?'
        )

        def repl(match):
            raw_number = match.group(1)
            if raw_number.isdigit():
                return f"{raw_number}%"
            try:
                return f"{self._word_to_number(raw_number)}%"
            except ValueError:
                return match.group(0)

        pattern = re.compile(
            r'(?i)\b(' + word_pattern + r'|\d+)\s+percent\b'
        )
        return pattern.sub(repl, text)

    def normalize_measurement_numerals(self, text: str) -> str:
        """Convert spelled-out numbers before abbreviated measurements into numerals."""
        word_pattern = (
            r'(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|'
            r'thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|'
            r'thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|'
            r'four|five|six|seven|eight|nine))?'
        )
        unit_pattern = '|'.join(sorted((re.escape(unit) for unit in self.MEASUREMENT_UNITS), key=len, reverse=True))

        def repl(match):
            raw_number = match.group(1)
            unit = match.group(2)
            try:
                return f"{self._word_to_number(raw_number)} {unit}"
            except ValueError:
                return match.group(0)

        pattern = re.compile(
            r'(?i)\b(' + word_pattern + r')\s+(' + unit_pattern + r')\b'
        )
        return pattern.sub(repl, text)

    def _normalize_author_name(self, name: str, profile: Dict[str, Any]) -> str:
        """Normalize a single author token to Vancouver-style surname + initials."""
        candidate = re.sub(r'\s+', ' ', name or '').strip().strip('.,;')
        if not candidate:
            return ''

        if re.fullmatch(r'et\s+al\.?', candidate, flags=re.IGNORECASE):
            return 'et al'

        if ',' in candidate:
            left, right = candidate.split(',', 1)
            left = left.strip()
            right = right.strip()
            if left and right:
                candidate = f'{left} {right}'

        tokens = [t for t in candidate.split(' ') if t]
        if not tokens:
            return candidate

        surname = self._normalize_author_surname_token(tokens[0])
        initials: List[str] = []
        tail_words: List[str] = []

        for token in tokens[1:]:
            clean = re.sub(r'[^A-Za-z]', '', token)
            if not clean:
                continue
            if len(clean) == 1:
                initials.append(clean.upper())
                continue
            if len(clean) <= 4 and clean.isupper():
                initials.extend(list(clean))
                continue
            # Keep full words if present; they are likely unresolved given names.
            tail_words.append(clean)

        if bool(profile.get("initials_with_periods")):
            initial_text = ''.join(f'{letter}.' for letter in initials)
        else:
            initial_text = ''.join(initials)

        out = surname
        if initial_text:
            out += f' {initial_text}'
        if tail_words:
            out += ' ' + ' '.join(tail_words)
        return out.strip()

    def _normalize_author_surname_token(self, value: str) -> str:
        """Normalize surname casing while preserving particles and punctuation."""
        token = str(value or "").strip()
        if not token:
            return token
        if token.isupper() and len(token) > 2:
            return token.title()
        if token.islower():
            return token.title()
        return token

    def _is_initials_fragment(self, value: str) -> bool:
        """Return True when one comma-fragment likely contains only initials."""
        raw = str(value or '').strip()
        if not raw:
            return False
        if re.fullmatch(r'(?:[A-Za-z]\.?(?:\s+|$)){1,4}', raw):
            return True
        cleaned = re.sub(r'[^A-Za-z]', '', raw)
        if not cleaned:
            return False
        return len(cleaned) <= 4 and cleaned.upper() == cleaned

    def _normalize_author_block(self, authors: str, profile: Dict[str, Any]) -> str:
        """Normalize a full author block while preserving order."""
        source = re.sub(r'\s+and\s+', ', ', authors, flags=re.IGNORECASE)
        source = source.replace('&', ', ')
        source = re.sub(r'\s+', ' ', source).strip().strip('.,;')
        if not source:
            return source

        raw_parts = [p.strip() for p in source.split(',') if p.strip()]
        stitched_parts: List[str] = []
        for raw in raw_parts:
            part = str(raw).strip()
            if self._is_initials_fragment(part) and stitched_parts:
                stitched_parts[-1] = f"{stitched_parts[-1]} {part}".strip()
            else:
                stitched_parts.append(part)

        if len(stitched_parts) == 2:
            second_clean = re.sub(r'[^A-Za-z]', '', stitched_parts[1])
            # Handle single-author "Surname, Initials" form.
            if second_clean.isupper() and 1 <= len(second_clean) <= 4:
                parts = [f'{stitched_parts[0]} {stitched_parts[1]}']
            else:
                parts = stitched_parts
        else:
            parts = stitched_parts

        normalized: List[str] = []
        for part in parts:
            normalized_part = self._normalize_author_name(part, profile)
            if normalized_part:
                normalized.append(normalized_part)

        if not normalized:
            return source

        if len(normalized) > 6 and not any(p.lower() == 'et al' for p in normalized):
            normalized = normalized[:6] + ['et al']

        return ', '.join(normalized)

    def _sentence_case_title(self, title: str) -> str:
        """Convert title to sentence case while preserving acronyms."""
        text = re.sub(r'\s+', ' ', title or '').strip().strip('.,;')
        if not text:
            return text

        tokens = re.split(r'(\s+)', text)
        out: List[str] = []
        first_alpha_done = False

        for token in tokens:
            if not token or token.isspace():
                out.append(token)
                continue

            match = re.match(r'^([^A-Za-z]*)([A-Za-z][A-Za-z\'\-]*)([^A-Za-z]*)$', token)
            if not match:
                out.append(token)
                continue

            prefix, word, suffix = match.groups()
            if word.isupper() and len(word) > 1:
                if word in self.TITLE_ACRONYMS:
                    normalized = word
                else:
                    normalized = word.lower()
                    if normalized in self.TITLE_PROPER_WORDS:
                        normalized = normalized.capitalize()
                    if not first_alpha_done:
                        normalized = normalized.capitalize()
            elif any(ch.isupper() for ch in word[1:]):
                normalized = word
            else:
                normalized = word.lower()
                if normalized in self.TITLE_PROPER_WORDS:
                    normalized = normalized.capitalize()
                if not first_alpha_done:
                    normalized = normalized.capitalize()

            if not first_alpha_done and re.search(r'[A-Za-z]', word):
                first_alpha_done = True

            out.append(prefix + normalized + suffix)

        return ''.join(out).strip()

    def _title_case_title(self, title: str) -> str:
        """Convert title to title case while preserving acronyms/proper words."""
        text = re.sub(r'\s+', ' ', title or '').strip().strip('.,;')
        if not text:
            return text

        tokens = re.split(r'(\s+)', text)
        alpha_positions = [idx for idx, tok in enumerate(tokens) if re.search(r'[A-Za-z]', tok or "")]
        if not alpha_positions:
            return text

        first_alpha_idx = alpha_positions[0]
        last_alpha_idx = alpha_positions[-1]
        out: List[str] = []

        for idx, token in enumerate(tokens):
            if not token or token.isspace():
                out.append(token)
                continue

            match = re.match(r'^([^A-Za-z]*)([A-Za-z][A-Za-z\'\-]*)([^A-Za-z]*)$', token)
            if not match:
                out.append(token)
                continue

            prefix, word, suffix = match.groups()
            lower = word.lower()

            if word in self.TITLE_ACRONYMS or (word.isupper() and len(word) > 1):
                normalized = word
            elif lower in self.TITLE_PROPER_WORDS:
                normalized = lower.capitalize()
            elif idx not in (first_alpha_idx, last_alpha_idx) and lower in self.TITLE_SMALL_WORDS:
                normalized = lower
            elif any(ch.isupper() for ch in word[1:]):
                normalized = word
            else:
                normalized = lower.capitalize()

            out.append(prefix + normalized + suffix)

        return ''.join(out).strip()

    def _abbreviate_journal_name(self, journal: str) -> str:
        """Abbreviate journal title using a deterministic NLM-like word map."""
        text = re.sub(r'\s+', ' ', journal or '').strip().strip('.,;')
        if not text:
            return text

        tokens = [t for t in text.split(' ') if t]
        result: List[str] = []

        for idx, token in enumerate(tokens):
            core = re.sub(r'[^A-Za-z&\-]', '', token)
            if not core:
                continue
            lower = core.lower()

            if idx > 0 and lower in self.JOURNAL_STOPWORDS:
                continue
            if lower in self.JOURNAL_ABBREVIATIONS:
                result.append(self.JOURNAL_ABBREVIATIONS[lower])
                continue
            if core.isupper():
                result.append(core)
                continue
            result.append(core.capitalize())

        return ' '.join(result).strip()

    def _normalize_reference_tail(self, tail: str) -> str:
        """Normalize trailing citation metadata to house journal style."""
        text = re.sub(r'\s+', ' ', tail or '').strip()
        if not text:
            return text

        doi_match = re.search(r'(?i)\b(?:doi:\s*)?(10\.\d{4,9}/[^\s<>"\']+)', text)
        doi_value = doi_match.group(1).rstrip('.,;') if doi_match else ''
        text_without_doi = text[:doi_match.start()].strip() if doi_match else text
        text_without_doi = text_without_doi.rstrip('.,; ')

        year_match = re.search(r'\b((?:19|20)\d{2})\b', text_without_doi)
        if not year_match:
            fallback = re.sub(r'\bdoi\s*:\s*', 'doi: ', text, flags=re.IGNORECASE)
            fallback = re.sub(r'\s{2,}', ' ', fallback).strip()
            return fallback

        year = year_match.group(1)
        remainder = text_without_doi[year_match.end():].strip()
        remainder = re.sub(r'^[A-Za-z]{3,9}\b(?:\s+\d{1,2})?,?\s*', '', remainder)
        remainder = re.sub(r'^\s*;\s*', '', remainder)
        remainder = re.sub(r'\s+', ' ', remainder).strip().rstrip('.')
        remainder = re.sub(r'\s*:\s*', ':', remainder)

        pieces = [f'{year} ;{remainder}' if remainder else year]
        if doi_value:
            pieces.append(f'doi: {doi_value}')
        return '. '.join(piece.rstrip('.').strip() for piece in pieces if piece).strip()

    def _normalize_book_tail(self, tail: str) -> str:
        """Normalize book metadata to canonical 'Place: Publisher; Year' form."""
        text = re.sub(r'\s+', ' ', tail or '').strip()
        if not text:
            return text

        text = text.strip().strip('.,;')
        text = re.sub(r'(?i)\s*[\(\[]?(?:19|20)\d{2}[\)\]]?\s*$', lambda m: m.group(0).strip("()[] "), text)
        year_match = re.search(r'\b((?:19|20)\d{2})\b', text)
        year = year_match.group(1) if year_match else ""
        pre_year = text[:year_match.start()].strip(" ,.;") if year_match else text

        place = ""
        publisher = ""
        place_pub = re.match(r'^(?P<place>[^:;]+?)\s*:\s*(?P<publisher>[^;]+?)\s*$', pre_year)
        if place_pub:
            place = (place_pub.group("place") or "").strip(" ,.;")
            publisher = (place_pub.group("publisher") or "").strip(" ,.;")
        else:
            comma_place_pub = re.match(r'^(?P<place>[^,;:]+?)\s*,\s*(?P<publisher>[^,;:]+?)\s*$', pre_year)
            if comma_place_pub:
                place = (comma_place_pub.group("place") or "").strip(" ,.;")
                publisher = (comma_place_pub.group("publisher") or "").strip(" ,.;")
            else:
                pub_only = re.match(r'^(?P<publisher>[^;:]+?)\s*$', pre_year)
                if pub_only:
                    publisher = (pub_only.group("publisher") or "").strip(" ,.;")

        segments: List[str] = []
        if place and publisher:
            segments.append(f"{place}: {publisher}")
        elif place:
            segments.append(f"{place}:")
        elif publisher:
            segments.append(publisher)
        if year:
            if segments:
                segments[-1] = f"{segments[-1]}; {year}"
            else:
                segments.append(year)

        normalized = ". ".join(part for part in segments if part).strip()
        if not normalized:
            normalized = text
        normalized = re.sub(r'\s{2,}', ' ', normalized).strip(" ,.;")
        return normalized

    def _missing_placeholder(self, field_label: str) -> str:
        """Return stable bracketed placeholder text for missing metadata."""
        return f'[{field_label} missing]'

    def _strip_missing_placeholders(self, text: str) -> str:
        """Remove synthetic missing-field placeholders before reparsing text."""
        cleaned = self.MISSING_PLACEHOLDER_RE.sub('', text or '')
        cleaned = re.sub(r'\s{2,}', ' ', cleaned)
        cleaned = re.sub(r'\s+([,;:.])', r'\1', cleaned)
        return cleaned.strip()

    def _detect_reference_source_type(self, entry: str, authors: str, title: str, journal: str, tail: str) -> str:
        """Classify a reference into coarse NLM source types for validation."""
        candidate = self._strip_missing_placeholders(re.sub(r'\s+', ' ', entry or '').strip())
        lower_candidate = candidate.lower()
        lower_journal = str(journal or "").lower()
        has_proceedings_marker = bool(
            re.search(r'(?i)\b(?:proceedings|proc\.?|spie|conference|symposium)\b', lower_candidate)
            or re.search(r'(?i)\b(?:proceedings|proc\.?|spie|conference|symposium)\b', lower_journal)
        )
        has_doi = bool(re.search(r'(?i)\b(?:doi:\s*)?10\.\d{4,9}/[^\s<>"\']+', candidate))
        if re.search(r'(?i)(?:^|[.])\s*In:?\s+', candidate):
            if has_proceedings_marker:
                return "proceedings"
            return "chapter"
        if re.search(r'(?i)\[Internet\]|Available from:|https?://|www\.', candidate):
            return "website"
        if has_proceedings_marker and (has_doi or re.search(r'(?i)\bVol\.?\s*\d+\b', candidate)):
            return "proceedings"
        if re.search(
            r'\)\.\s*[^.]+\.\s*[^,]+,\s*[A-Za-z]?\d+(?:\([^)]+\))?\s*,\s*[A-Za-z]?\d+(?:\s*[-–]\s*[A-Za-z]?\d+)?',
            candidate
        ):
            return "journal"
        if re.search(r'\b(?:19|20)\d{2}(?:\s+[A-Za-z]{3,9}(?:\s+\d{1,2})?)?\s*;\s*[A-Za-z]?\d+(?:\([^)]+\))?', candidate):
            return "journal"
        if re.search(r':\s*[A-Za-z]?\d+(?:\s*[-–]\s*[A-Za-z]?\d+)?\b', candidate) and journal:
            return "journal"
        if has_doi:
            if has_proceedings_marker:
                return "proceedings"
            return "journal"
        if re.search(r'(?i)\b\d+(?:st|nd|rd|th)\s+ed\.?\b', candidate):
            return "book"
        if re.search(r'[^.;\[\]]+:\s*[^.;\[\]]+(?:\s*;\s*(?:19|20)\d{2})?', candidate):
            return "book"
        if journal and re.search(r'(?i)\b(?:j|journal|int|international|proc|proceedings|med|clin|res|rev|sci|test)\b', journal):
            return "journal"
        if tail and re.fullmatch(r'(?:19|20)\d{2}\.?', tail.strip()):
            return "book"
        if journal and tail:
            return "journal"
        if tail:
            return "book"
        if authors or title:
            return "book"
        return "generic"

    def _analyze_reference_entry(self, entry: str) -> Dict[str, Any]:
        """Return parsed reference metadata for source-type-aware validation."""
        candidate = self._strip_missing_placeholders(
            self._pre_normalize_reference_entry_line(re.sub(r'\s+', ' ', entry or '').strip())
        )
        authors, title, journal, tail = self._split_reference_entry_parts(candidate)
        source_type = self._detect_reference_source_type(candidate, authors, title, journal, tail)

        if source_type == "chapter":
            chapter_parts = re.split(r'(?i)\bIn:\s*', candidate, maxsplit=1)
            prefix = chapter_parts[0].strip()
            suffix = chapter_parts[1].strip() if len(chapter_parts) > 1 else ""
            prefix_segments = [
                part.strip().strip('.,;')
                for part in re.split(r'\.\s+(?=[A-Za-z])', prefix)
                if part.strip()
            ]
            authors = prefix_segments[0] if prefix_segments else ""
            title = prefix_segments[1] if len(prefix_segments) > 1 else ""
            journal = suffix

        place_publisher_match = re.search(
            r'(?P<place>[^.;\[\]]+?)\s*:\s*(?P<publisher>[^.;\[\]]+?)(?:\s*;\s*(?P<year>(?:19|20)\d{2}))?(?=(?:\s*\[cited|\s*Available from:|\.|$))',
            candidate,
            flags=re.IGNORECASE,
        )
        publisher_year_match = re.search(
            r'(?P<publisher>[^.;\[\]]+?)\s*;\s*(?P<year>(?:19|20)\d{2})(?=(?:\s*\[cited|\s*Available from:|\.|$))',
            candidate,
            flags=re.IGNORECASE,
        )
        year_match = re.search(r'\b(?:19|20)\d{2}\b', candidate)
        volume_match = re.search(
            r'\b(?:19|20)\d{2}(?:\s+[A-Za-z]{3,9}(?:\s+\d{1,2})?)?\s*;\s*(?P<volume>[A-Za-z]?\d+(?:\([^)]+\))?)',
            candidate
        ) or re.search(
            r'\)\.\s*[^.]+\.\s*[^,]+,\s*(?P<volume>[A-Za-z]?\d+(?:\([^)]+\))?)\s*,\s*[A-Za-z]?\d+(?:\s*[-–]\s*[A-Za-z]?\d+)?',
            candidate
        )
        page_match = re.search(
            r'(?::\s*(?P<pages>[A-Za-z]?\d+(?:\s*[-–]\s*[A-Za-z]?\d+)?))\b',
            candidate,
        ) or re.search(
            r',\s*[A-Za-z]?\d+(?:\([^)]+\))?\s*,\s*(?P<pages>[A-Za-z]?\d+(?:\s*[-–]\s*[A-Za-z]?\d+)?)\b',
            candidate,
        ) or re.search(r'(?i)\bp(?:p)?\.?\s*(?P<pages>\d+(?:\s*[-–]\s*\d+)?)\b', candidate)
        cited_match = re.search(r'(?i)\[cited [^\]]+\]', candidate)
        url_match = re.search(r'(?i)(https?://\S+|www\.\S+)', candidate)
        doi_match = re.search(r'(?i)\b(?:doi:\s*)?10\.\d{4,9}/[^\s<>"\']+', candidate)
        has_editor = re.search(r'(?i)\b(?:ed\.|eds\.|editor|editors)\b', candidate) is not None

        return {
            "entry": candidate,
            "source_type": source_type,
            "authors": authors,
            "title": title,
            "journal": journal,
            "tail": tail,
            "year": year_match.group(0) if year_match else "",
            "volume": volume_match.group("volume") if volume_match and volume_match.groupdict().get("volume") else "",
            "pages": page_match.group("pages") if page_match and page_match.groupdict().get("pages") else "",
            "url": url_match.group(1).rstrip(".,;") if url_match else "",
            "doi": doi_match.group(0).replace("doi:", "").strip().rstrip(".,;") if doi_match else "",
            "has_author": bool(re.search(r'[A-Za-z]', authors or "")),
            "has_title": bool(re.search(r'[A-Za-z]', title or "")),
            "has_journal": bool(re.search(r'[A-Za-z]', journal or "")),
            "has_year": year_match is not None,
            "has_volume": volume_match is not None,
            "has_pages": page_match is not None,
            "has_doi": doi_match is not None,
            "has_url": url_match is not None,
            "has_cited_date": cited_match is not None,
            "has_editor": has_editor,
            "has_place": bool(place_publisher_match and re.search(r'[A-Za-z]', place_publisher_match.group('place') or "")),
            "has_publisher": bool(
                (place_publisher_match and re.search(r'[A-Za-z]', place_publisher_match.group('publisher') or ""))
                or (publisher_year_match and re.search(r'[A-Za-z]', publisher_year_match.group('publisher') or ""))
            ),
        }

    def _reference_missing_specs(self, metadata: Dict[str, Any]) -> List[Dict[str, str]]:
        """Return required-field rules for a reference based on detected source type."""
        source_type = str(metadata.get("source_type") or "generic")
        has_contributor = bool(metadata.get("has_author")) or bool(metadata.get("has_editor"))

        if source_type in {"journal", "proceedings"}:
            checks = [
                ("author", "reference_missing_author", "reference_missing_author_numbers", bool(metadata.get("has_author"))),
                ("title", "reference_missing_title", "reference_missing_title_numbers", bool(metadata.get("has_title"))),
                ("journal", "reference_missing_journal", "reference_missing_journal_numbers", bool(metadata.get("has_journal"))),
                ("year", "reference_missing_year", "reference_missing_year_numbers", bool(metadata.get("has_year"))),
                ("volume", "reference_missing_volume", "reference_missing_volume_numbers", bool(metadata.get("has_volume"))),
                ("page", "reference_missing_pages", "reference_missing_pages_numbers", bool(metadata.get("has_pages"))),
            ]
        elif source_type == "website":
            checks = [
                ("author", "reference_missing_author", "reference_missing_author_numbers", has_contributor),
                ("title", "reference_missing_title", "reference_missing_title_numbers", bool(metadata.get("has_title"))),
                ("year", "reference_missing_year", "reference_missing_year_numbers", bool(metadata.get("has_year"))),
                ("cited date", "reference_missing_cited_date", "reference_missing_cited_date_numbers", bool(metadata.get("has_cited_date"))),
                ("url", "reference_missing_url", "reference_missing_url_numbers", bool(metadata.get("has_url"))),
            ]
        elif source_type == "chapter":
            checks = [
                ("author", "reference_missing_author", "reference_missing_author_numbers", bool(metadata.get("has_author"))),
                ("title", "reference_missing_title", "reference_missing_title_numbers", bool(metadata.get("has_title"))),
                ("editor", "reference_missing_editor", "reference_missing_editor_numbers", bool(metadata.get("has_editor"))),
                ("place", "reference_missing_place", "reference_missing_place_numbers", bool(metadata.get("has_place"))),
                ("publisher", "reference_missing_publisher", "reference_missing_publisher_numbers", bool(metadata.get("has_publisher"))),
                ("year", "reference_missing_year", "reference_missing_year_numbers", bool(metadata.get("has_year"))),
                ("page", "reference_missing_pages", "reference_missing_pages_numbers", bool(metadata.get("has_pages"))),
            ]
        else:
            checks = [
                ("author", "reference_missing_author", "reference_missing_author_numbers", has_contributor),
                ("title", "reference_missing_title", "reference_missing_title_numbers", bool(metadata.get("has_title"))),
                ("place", "reference_missing_place", "reference_missing_place_numbers", bool(metadata.get("has_place"))),
                ("publisher", "reference_missing_publisher", "reference_missing_publisher_numbers", bool(metadata.get("has_publisher"))),
                ("year", "reference_missing_year", "reference_missing_year_numbers", bool(metadata.get("has_year"))),
            ]

        return [
            {"label": label, "code": code, "detail_key": detail_key}
            for label, code, detail_key, present in checks
            if not present
        ]

    def _split_reference_entry_parts(self, entry: str) -> Tuple[str, str, str, str]:
        """Split one reference into (authors, title, journal, tail)."""
        candidate = self._strip_missing_placeholders(
            self._pre_normalize_reference_entry_line(re.sub(r'\s+', ' ', entry or '').strip())
        )
        if not candidate:
            return "", "", "", ""

        apa_journal_match = re.match(
            r'^(?P<authors>.+?)\s*\((?P<year>(?:19|20)\d{2})\)\.\s*'
            r'(?P<title>.+?)\.\s*'
            r'(?P<journal>.+?),\s*'
            r'(?P<volume>[A-Za-z]?\d+(?:\([^)]+\))?)\s*,\s*'
            r'(?P<pages>[A-Za-z]?\d+(?:\s*[-–]\s*[A-Za-z]?\d+)?)'
            r'\.?\s*(?P<rest>.*)$',
            candidate,
        )
        if apa_journal_match:
            authors = apa_journal_match.group('authors').strip().strip('.,;')
            title = apa_journal_match.group('title').strip().strip('.,;')
            journal = apa_journal_match.group('journal').strip().strip('.,;')
            tail = f"{apa_journal_match.group('year')} ;{apa_journal_match.group('volume')}:{apa_journal_match.group('pages')}"
            rest = str(apa_journal_match.group('rest') or '').strip().strip('.,;')
            if rest:
                tail += f". {rest}"
            return authors, title, journal, tail

        author_year_title_url_match = re.match(
            r'^(?P<authors>.+?)\s*(?:\((?P<year1>(?:19|20)\d{2})\)|(?P<year2>(?:19|20)\d{2}))'
            r'[.;]?\s*(?P<title>.+?)\.\s*(?P<url>(?:https?://\S+|www\.\S+))\.?$',
            candidate,
            flags=re.IGNORECASE,
        )
        if author_year_title_url_match:
            authors = author_year_title_url_match.group('authors').strip().strip('.,;')
            title = author_year_title_url_match.group('title').strip().strip('.,;')
            year = str(author_year_title_url_match.group('year1') or author_year_title_url_match.group('year2') or '').strip()
            url = str(author_year_title_url_match.group('url') or '').strip()
            tail = year
            if url:
                tail = f"{tail}. Available from: {url}" if tail else f"Available from: {url}"
            return authors, title, "", tail

        year_match = re.search(r'\b(?:19|20)\d{2}\b', candidate)
        if year_match:
            before_year = candidate[:year_match.start()].strip().strip('.,;')
            tail = candidate[year_match.start():].strip()
        else:
            before_year = candidate.strip().strip('.,;')
            tail = ''

        segments = [
            part.strip().strip('.,;')
            for part in re.split(r'\.\s+(?=[A-Za-z])', before_year)
            if part.strip()
        ]
        authors = segments[0] if segments else before_year
        title = segments[1] if len(segments) > 1 else ''
        journal = '. '.join(segments[2:]) if len(segments) > 2 else ''
        return authors, title, journal, tail

    def _format_reference_title(self, title: str, profile: Dict[str, Any]) -> str:
        """Format reference title by selected profile rule."""
        mode = str(profile.get("title_case", "sentence")).strip().lower()
        if mode == "title":
            return self._title_case_title(title)
        return self._sentence_case_title(title)

    def _format_reference_journal(self, journal: str, profile: Dict[str, Any]) -> str:
        """Format journal title (NLM abbreviation or full title) by profile."""
        mode = str(profile.get("journal_abbrev", "nlm")).strip().lower()
        if mode == "full":
            return self._title_case_title(journal)
        return self._abbreviate_journal_name(journal)

    def _normalize_reference_entry(self, entry: str, profile: Dict[str, Any]) -> str:
        """Normalize a single reference entry to configured Vancouver style."""
        candidate = self._strip_missing_placeholders(
            self._pre_normalize_reference_entry_line(re.sub(r'\s+', ' ', entry or '').strip())
        )
        if not candidate:
            return candidate

        metadata = self._analyze_reference_entry(candidate)
        authors, title, journal, tail = self._split_reference_entry_parts(candidate)

        if str(metadata.get("source_type") or "") == "journal":
            authors_norm = self._normalize_author_block(authors, profile)
            title_norm = self._format_reference_title(title, profile) if title else ''
            journal_norm = self._format_reference_journal(journal, profile) if journal else ''
            tail_norm = self._normalize_reference_tail(tail)

            third_segment = ''
            if journal_norm and tail_norm:
                third_segment = f'{journal_norm.rstrip(".")}. {tail_norm}'.strip()
            elif journal_norm:
                third_segment = journal_norm
            else:
                third_segment = tail_norm

            pieces = [p.rstrip('.') for p in [authors_norm, title_norm, third_segment] if p]
            normalized = '. '.join(pieces).strip()
            normalized = re.sub(r'\s+([,:.])', r'\1', normalized)
            normalized = re.sub(r'\s{2,}', ' ', normalized).strip()
        elif str(metadata.get("source_type") or "") == "book":
            authors_norm = self._normalize_author_block(authors, profile) if authors else ''
            title_norm = self._format_reference_title(title, profile) if title else ''
            book_tail_seed = tail
            journal_hint = (journal or "").strip().strip(".")
            # If parser treated place/publisher as "journal" and tail is just year,
            # stitch them back so book-tail normalization can recover `place: publisher; year`.
            if journal_hint and re.fullmatch(r'\s*(?:19|20)\d{2}\.?\s*', str(tail or '')):
                if ',' in journal_hint:
                    book_tail_seed = f"{journal_hint}; {str(tail or '').strip().rstrip('.')}"
                elif ';' not in journal_hint:
                    book_tail_seed = f"{journal_hint}; {str(tail or '').strip().rstrip('.')}"
            tail_norm = self._normalize_book_tail(book_tail_seed)
            segments = [part.rstrip('.') for part in [authors_norm, title_norm] if part]
            if tail_norm:
                segments.append(tail_norm)
            normalized = '. '.join(part for part in segments if part).strip()
            normalized = re.sub(r'\s{2,}', ' ', normalized).strip()
        else:
            normalized = candidate
            if authors:
                authors_norm = self._normalize_author_block(authors, profile)
                if authors_norm and normalized.startswith(authors):
                    remainder = normalized[len(authors):]
                    if authors_norm.endswith('.') and remainder.startswith('.'):
                        remainder = remainder[1:]
                    normalized = (authors_norm + remainder).strip()
            normalized = re.sub(r'(?i)\[internet\]', '[Internet]', normalized)
            normalized = re.sub(r'(?i)available from:', 'Available from:', normalized)
            normalized = re.sub(r'\s{2,}', ' ', normalized).strip()

        if normalized and not normalized.endswith('.'):
            normalized += '.'
        metadata_post = self._analyze_reference_entry(normalized)
        placeholder_injected = self._inject_missing_placeholders_inline(normalized, metadata_post)
        final_shape = self._finalize_reference_shape(placeholder_injected, metadata_post, profile)
        return str(final_shape.get("entry") or placeholder_injected)

    def _reference_shape_templates(self) -> Dict[str, str]:
        """Human-readable reference shape templates by source type."""
        return {
            "journal": "Author AB, Author CD. Title in sentence case. J Abbrev. 2024;10(2):100-110. doi: 10.xxxx/xxxxx.",
            "proceedings": "Author AB, Author CD. Title in sentence case. In: Proceedings/Event title. 2024;Vol. 12107:13-20. doi: 10.xxxx/xxxxx.",
            "book": "Author AB. Book title in sentence case. Place: Publisher; 2024.",
            "chapter": "Author AB. Chapter title. In: Editor AB, editor. Book title. Place: Publisher; 2024. p. 100-110.",
            "website": "Organization or Author AB. Page title [Internet]. Place: Publisher; 2024 [cited 2026 May 09]. Available from: https://example.org.",
            "generic": "Author AB. Title. 2024.",
        }

    def _final_shape_check(self, source_type: str, entry: str) -> Tuple[bool, List[str]]:
        """Validate reference against coarse end-shape expectations."""
        text = re.sub(r'\s+', ' ', str(entry or '')).strip()
        if not text:
            return False, ["empty reference entry"]

        reasons: List[str] = []
        if not re.search(r'\b(?:19|20)\d{2}\b', text):
            reasons.append("missing year")

        normalized_type = source_type if source_type in {"journal", "proceedings", "book", "chapter", "website"} else "generic"
        if normalized_type in {"journal", "proceedings"}:
            if not re.search(r'\s*;\s*[A-Za-z]?\d+(?:\([^)]+\))?\s*:\s*[A-Za-z]?\d+(?:\s*[-–]\s*[A-Za-z]?\d+)?', text):
                if normalized_type == "proceedings":
                    if not re.search(r'(?i)\bVol\.?\s*\d+\b', text):
                        reasons.append("missing or malformed volume/pages segment")
                else:
                    reasons.append("missing or malformed volume/pages segment")
            if not re.search(r'\.\s+[A-Za-z].+\.\s+(?:19|20)\d{2}\s*;', text):
                if normalized_type == "proceedings" and re.search(r'(?i)\b(?:proceedings|spie|conference)\b', text):
                    pass
                else:
                    reasons.append("journal sequence should be title. journal. year;volume:pages")
        elif normalized_type == "book":
            if not re.search(r'[^.;]+:\s*[^.;]+;\s*(?:19|20)\d{2}', text) and not re.search(r'\[place missing\]\s*:\s*[^.;]+;\s*(?:19|20)\d{2}', text):
                reasons.append("book entry should contain place: publisher; year")
        elif normalized_type == "chapter":
            if not re.search(r'(?i)\bIn:\s*', text):
                reasons.append("chapter entry missing In: editor block")
            if not re.search(r'[^.;]+:\s*[^.;]+;\s*(?:19|20)\d{2}', text):
                reasons.append("chapter entry missing place: publisher; year")
        elif normalized_type == "website":
            if "[Internet]" not in text:
                reasons.append("website entry missing [Internet] marker")
            if not re.search(r'(?i)\bAvailable from:\s*(https?://\S+|www\.\S+)', text):
                reasons.append("website entry missing Available from URL")
            if not re.search(r'(?i)\[cited [^\]]+\]', text):
                reasons.append("website entry missing cited date")

        return len(reasons) == 0, reasons

    def _attempt_final_shape_repair(self, source_type: str, entry: str) -> str:
        """Apply conservative final-shape repairs before manual-review fallback."""
        text = re.sub(r'\s+', ' ', str(entry or '')).strip()
        if not text:
            return text

        if source_type == "website":
            if "[Internet]" not in text:
                text = re.sub(
                    r'^(\s*(?:[^.]+\.)\s*)(.+?)\.\s*',
                    lambda m: f"{m.group(1)}{m.group(2)} [Internet]. ",
                    text,
                    count=1,
                )
            if not re.search(r'(?i)\[cited [^\]]+\]', text):
                year_match = re.search(r'\b(?:19|20)\d{2}\b', text)
                if year_match:
                    idx = year_match.end()
                    text = f"{text[:idx]} [cited date missing]{text[idx:]}"
                else:
                    text = text.rstrip(". ") + " [cited date missing]."
            if re.search(r'(?i)\bAvailable from:\s*$', text):
                text += " [url missing]"
        elif source_type in {"book", "chapter"}:
            # Preserve existing author/title/journal-like strings when DOI-backed lines
            # look like journal/proceedings references; avoid destructive reshaping.
            if re.search(r'(?i)\b(?:doi:\s*)?10\.\d{4,9}/[^\s<>"\']+', text) and re.search(r'(?i)\b(?:journal|science|ieee|proceedings|conference|spie)\b', text):
                return text if text.endswith('.') else f"{text}."
            text = re.sub(
                r'(?P<place>[^.;,\[\]]+?)\s*,\s*(?P<publisher>[^.;,\[\]]+?)\s*,\s*(?P<year>(?:19|20)\d{2})',
                lambda m: f"{m.group('place').strip()}: {m.group('publisher').strip()}; {m.group('year').strip()}",
                text,
                count=1,
            )
        elif source_type in {"journal", "proceedings"}:
            volpg = re.search(r';\s*[A-Za-z]?\d+(?:\([^)]+\))?\s*:\s*[A-Za-z]?\d+\s*[-–]\s*[A-Za-z]?\d+', text)
            if not volpg:
                year_match = re.search(r'\b(?:19|20)\d{2}\b', text)
                if year_match:
                    text = text[:year_match.end()] + ";[volume missing]:[page missing]." + text[year_match.end():]

        text = re.sub(r'\s{2,}', ' ', text).strip()
        text = re.sub(r'\s+([,:.])', r'\1', text)
        if text and not text.endswith('.'):
            text += '.'
        return text

    def _finalize_reference_shape(self, entry: str, metadata: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
        """Run final shape validation/repair and mark irreparable entries for manual review."""
        _ = profile  # Reserved for future profile-specific shape strictness.
        source_type = str((metadata or {}).get("source_type") or "generic")
        candidate = re.sub(r'\s+', ' ', str(entry or '')).strip()
        passed, reasons = self._final_shape_check(source_type, candidate)
        if passed:
            return {"entry": candidate, "passed": True, "repaired": False, "reasons": []}

        repaired = self._attempt_final_shape_repair(source_type, candidate)
        repaired_ok, repaired_reasons = self._final_shape_check(source_type, repaired)
        if repaired_ok:
            return {"entry": repaired, "passed": True, "repaired": True, "reasons": reasons}

        reason_text = ", ".join(repaired_reasons[:3]) if repaired_reasons else "shape mismatch"
        flagged = repaired.rstrip(". ")
        flagged += f". [needs manual review: {reason_text}]."
        return {"entry": flagged, "passed": False, "repaired": True, "reasons": repaired_reasons or reasons}

    def _inject_missing_placeholders_inline(self, text: str, metadata: Dict[str, Any]) -> str:
        """Insert missing-field placeholders near their expected field position."""
        result = re.sub(r'\s+', ' ', text or '').strip()
        if not result:
            return result

        for spec in self._reference_missing_specs(metadata):
            label = str(spec.get("label") or "")
            code = str(spec.get("code") or "")
            placeholder = self._missing_placeholder(label)
            if placeholder.lower() in result.lower():
                continue
            result = self._insert_missing_placeholder(result, code, placeholder)

        result = re.sub(r'\s{2,}', ' ', result).strip()
        result = re.sub(r'\s+([,:.])', r'\1', result)
        if result and not result.endswith('.'):
            result += '.'
        return result

    def _insert_missing_placeholder(self, text: str, code: str, placeholder: str) -> str:
        """Insert one placeholder for a specific missing-field code."""
        working = text.strip()

        if code == "reference_missing_author":
            if re.match(r'^\s*\[[A-Za-z][A-Za-z ]* missing\]', working, flags=re.IGNORECASE):
                return working
            return f"{placeholder}. {working}".strip()

        if code == "reference_missing_title":
            first_sentence = re.match(r'^\s*([^\.]+\.)(?:\s*(.*))?$', working)
            if first_sentence:
                head = first_sentence.group(1).strip()
                tail = (first_sentence.group(2) or '').strip()
                if tail:
                    return f"{head} {placeholder}. {tail}".strip()
                return f"{head} {placeholder}.".strip()
            return f"{placeholder}. {working}".strip()

        if code == "reference_missing_journal":
            year_match = re.search(r'\b(?:19|20)\d{2}\b', working)
            if year_match:
                left = working[:year_match.start()].rstrip().rstrip('.')
                right = working[year_match.start():].lstrip()
                return f"{left}. {placeholder}. {right}".strip()
            return working.rstrip('. ') + f" {placeholder}."

        if code == "reference_missing_year":
            vol_match = re.search(r';\s*[A-Za-z]?\d+(?:\([^)]+\))?', working)
            if vol_match:
                return (working[:vol_match.start()] + f" {placeholder}" + working[vol_match.start():]).strip()
            return re.sub(
                r'(?i)\s*Available from:',
                f" {placeholder}. Available from:",
                working,
                count=1,
            ) if re.search(r'(?i)Available from:', working) else working.rstrip('. ') + f"; {placeholder}."

        if code == "reference_missing_volume":
            year_match = re.search(r'\b(?:19|20)\d{2}\b', working)
            if year_match:
                at = year_match.end()
                return (working[:at] + f";{placeholder}" + working[at:]).strip()
            return working.rstrip('. ') + f";{placeholder}."

        if code == "reference_missing_pages":
            vol_match = re.search(r';\s*[A-Za-z]?\d+(?:\([^)]+\))?', working)
            if vol_match:
                at = vol_match.end()
                return (working[:at] + f":{placeholder}" + working[at:]).strip()
            if re.search(r'(?i)\bIn:\s*', working):
                return working.rstrip('. ') + f" p. {placeholder}."
            return working.rstrip('. ') + f" {placeholder}."

        if code == "reference_missing_place":
            pub_year = re.search(
                r'(?P<lead>\s*)(?P<publisher>[^.;\[\]]+?)\s*;\s*(?P<year>(?:19|20)\d{2})',
                working,
                flags=re.IGNORECASE,
            )
            if pub_year:
                lead = ' ' if (pub_year.group('lead') or '') else ''
                publisher = (pub_year.group('publisher') or '').strip()
                year = (pub_year.group('year') or '').strip()
                replacement = f"{lead}{placeholder}: {publisher}; {year}"
                return (working[:pub_year.start()] + replacement + working[pub_year.end():]).strip()
            return working.rstrip('. ') + f" {placeholder}."

        if code == "reference_missing_publisher":
            place_year = re.search(
                r'(?P<lead>\s*)(?P<place>[^.;\[\]]+?)\s*;\s*(?P<year>(?:19|20)\d{2})',
                working,
                flags=re.IGNORECASE,
            )
            if place_year:
                lead = ' ' if (place_year.group('lead') or '') else ''
                place = (place_year.group('place') or '').strip()
                year = (place_year.group('year') or '').strip()
                replacement = f"{lead}{place}: {placeholder}; {year}"
                return (working[:place_year.start()] + replacement + working[place_year.end():]).strip()
            return working.rstrip('. ') + f" {placeholder}."

        if code == "reference_missing_editor":
            if re.search(r'(?i)\bIn:\s*', working):
                return re.sub(r'(?i)\bIn:\s*', f'In: {placeholder}, editor. ', working, count=1).strip()
            return working.rstrip('. ') + f" In: {placeholder}, editor."

        if code == "reference_missing_cited_date":
            if re.search(r'(?i)\[cited [^\]]+\]', working):
                return working
            if re.search(r'(?i)Available from:', working):
                dotted = re.sub(
                    r'(?i)\.\s*Available from:',
                    f' {placeholder}. Available from:',
                    working,
                    count=1,
                ).strip()
                if dotted != working:
                    return dotted
                return re.sub(
                    r'(?i)\s*Available from:',
                    f' {placeholder}. Available from:',
                    working,
                    count=1,
                ).strip()
            year_match = re.search(r'\b(?:19|20)\d{2}\b', working)
            if year_match:
                at = year_match.end()
                return (working[:at] + f" {placeholder}" + working[at:]).strip()
            return working.rstrip('. ') + f" {placeholder}."

        if code == "reference_missing_url":
            if re.search(r'(?i)(https?://\S+|www\.\S+)', working):
                return working
            if re.search(r'(?i)Available from:\s*$', working):
                return working + f" {placeholder}"
            if re.search(r'(?i)Available from:\s*', working):
                return re.sub(r'(?i)Available from:\s*', f'Available from: {placeholder} ', working, count=1).strip()
            return working.rstrip('. ') + f". Available from: {placeholder}."

        return working.rstrip('. ') + f" {placeholder}."

    def _extract_reference_entries(self, text: str) -> List[str]:
        """Extract normalized reference lines from references section."""
        lines = (text or "").split('\n')
        entries: List[str] = []
        in_references = False
        current_index = -1

        heading_re = re.compile(r'^\s*references?\s*:?\s*$', flags=re.IGNORECASE)
        leading_marker_re = re.compile(r'^\s*(?:\[\s*\d+\s*\]|\d+\s*[.)])\s*')
        section_break_re = re.compile(
            r'^\s*(?:appendix|acknowledg(?:e)?ments?|funding|conflicts?\s+of\s+interest|author\s+contributions?)\s*:?\s*$',
            flags=re.IGNORECASE
        )
        continuation_re = re.compile(
            r'^(?:https?://|www\.|doi:\s*10\.|10\.\d{4,9}/|available\s+from|accessed\b|pmid\b|pmcid\b|epub\b)',
            flags=re.IGNORECASE
        )

        for line in lines:
            if heading_re.match(line):
                in_references = True
                current_index = -1
                continue

            if in_references and section_break_re.match(line):
                in_references = False
                current_index = -1
                continue

            if not in_references:
                continue

            stripped = line.strip()
            if not stripped:
                current_index = -1
                continue

            cleaned = leading_marker_re.sub('', stripped)
            is_continuation = (
                current_index >= 0 and
                (
                    line[:1].isspace() or
                    continuation_re.match(cleaned) is not None
                )
            )
            if is_continuation:
                entries[current_index] = entries[current_index].rstrip() + ' ' + cleaned
                continue

            entries.append(self._pre_normalize_reference_entry_line(cleaned))
            current_index = len(entries) - 1

        return entries

    def _pre_normalize_reference_entry_line(self, entry: str) -> str:
        """Repair common mixed-format reference issues before parsing/classification."""
        text = re.sub(r'\s+', ' ', str(entry or '')).strip()
        if not text:
            return text

        # Normalize author separators and accidental lowercase initials fragments.
        text = re.sub(r'\s*&\s*', ', ', text)
        text = re.sub(r',\s*([a-z])\.', lambda m: f", {m.group(1).upper()}.", text)
        text = re.sub(r'([A-Za-z])\.\s*,\s*([A-Za-z])\.', r'\1. \2.', text)

        # Ensure "In:" marker is consistently punctuated.
        text = re.sub(r'(?i)\bIn\s+', 'In: ', text)
        text = re.sub(r'(?i)\bIn:\s*In:\s*', 'In: ', text)

        # APA-like comma before pages => Vancouver-like colon.
        text = re.sub(
            r'(\b(?:19|20)\d{2}\s*;\s*[A-Za-z]?\d+(?:\([^)]+\))?)\s*,\s*([A-Za-z]?\d+(?:\s*[-–]\s*[A-Za-z]?\d+)?)\b',
            r'\1:\2',
            text,
        )

        # Repair malformed punctuation around year/volume/page tokens.
        text = re.sub(r'(\b(?:19|20)\d{2})\s*;\s*\[volume missing\]\s*;\s*', r'\1;[volume missing]:', text)
        text = re.sub(r'(\b(?:19|20)\d{2})\s*;\s*\)\s*;', r'\1;', text)
        text = re.sub(r'\s+:\s*', ':', text)
        text = re.sub(r'\s+;\s*', ';', text)
        text = re.sub(r';(?=[A-Za-z0-9])', '; ', text)
        text = re.sub(r':(?=[A-Za-z0-9\[])', ':', text)

        # Canonical DOI label spacing.
        text = re.sub(r'(?i)\bdoi\s*:\s*', 'doi: ', text)
        text = re.sub(r'\s{2,}', ' ', text).strip()
        return text

    def append_online_reference_links(
        self,
        text: str,
        citation_report: Optional[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Append validated DOI/source links to numbered references when available."""
        content = str(text or "")
        if not content.strip():
            return content

        online = {}
        if isinstance(citation_report, dict):
            online = citation_report.get("online_validation") if isinstance(citation_report.get("online_validation"), dict) else {}
        if not online or not bool(online.get("enabled", False)):
            return content
        if not bool((options or {}).get("online_reference_validation", False)):
            return content

        enrichment = {
            "enabled": True,
            "strict_doi_mode": bool((options or {}).get("strict_doi_mode", True)),
            "doi_mode": str((options or {}).get("doi_insertion_mode", "balanced")).strip().lower(),
            "auto_resolve_enabled": bool((options or {}).get("auto_resolve_unresolved_references", True)),
            "references_considered": 0,
            "fields_filled": 0,
            "fields_filled_by_type": {},
            "autofill_full": 0,
            "autofill_partial": 0,
            "autofill_none": 0,
            "auto_resolved": 0,
            "still_unresolved": 0,
            "confidence_rejected": 0,
            "doi_inserted": 0,
            "doi_needs_review_inserted": 0,
            "doi_override_inserted": 0,
            "doi_rejected": 0,
            "rejected_numbers": [],
            "trail": [],
        }

        online_entries = online.get("entries", []) if isinstance(online.get("entries"), list) else []
        for raw_entry in online_entries:
            if not isinstance(raw_entry, dict):
                continue
            if bool(raw_entry.get("auto_resolved")):
                enrichment["auto_resolved"] += 1
            if bool(raw_entry.get("confidence_rejected")):
                enrichment["confidence_rejected"] += 1
            status_value = str(raw_entry.get("status") or "").strip().lower()
            if status_value in {"ambiguous", "not_found", "mismatch", "error"}:
                enrichment["still_unresolved"] += 1

        validated_by_number: Dict[int, Dict[str, Any]] = {}
        for entry in online_entries:
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status") or "").strip().lower()
            if status not in {"verified", "likely_match"}:
                continue
            try:
                number = int(entry.get("number") or 0)
            except Exception:
                number = 0
            if number <= 0:
                continue
            validated_by_number[number] = entry
        online["enrichment"] = enrichment
        if not validated_by_number:
            return content

        lines = content.split('\n')
        output: List[str] = []
        in_references = False
        heading_re = re.compile(r'^\s*references?\s*:?\s*$', flags=re.IGNORECASE)
        section_break_re = re.compile(
            r'^\s*(?:appendix|acknowledg(?:e)?ments?|funding|conflicts?\s+of\s+interest|author\s+contributions?)\s*:?\s*$',
            flags=re.IGNORECASE,
        )
        numbered_reference_re = re.compile(r'^(\s*\[\s*(\d+)\s*\]\s*)(.*)$')

        for line in lines:
            if heading_re.match(line):
                in_references = True
                output.append(line)
                continue
            if in_references and section_break_re.match(line):
                in_references = False
                output.append(line)
                continue
            if not in_references:
                output.append(line)
                continue

            match = numbered_reference_re.match(line)
            if not match:
                output.append(line)
                continue

            prefix = match.group(1)
            number = int(match.group(2))
            entry_text = str(match.group(3) or "").strip()
            validated = validated_by_number.get(number)
            if not validated:
                output.append(line)
                continue

            fixability_filter = str((options or {}).get("unresolved_fixability_filter") or "all").strip().lower()
            if fixability_filter == "auto_fixable":
                validation_status = str(validated.get("status") or "").strip().lower()
                # Safe mode: only retry entries likely to be resolved automatically.
                if validation_status not in {"verified", "likely_match"}:
                    output.append(line)
                    continue

            enrichment["references_considered"] += 1
            entry_metadata = self._analyze_reference_entry(entry_text)
            matched_source_type = str(validated.get("matched_source_type") or "").strip().lower()
            if matched_source_type in {"journal", "proceedings", "book", "chapter", "website"}:
                entry_metadata["source_type"] = matched_source_type
            manual_reason_match = re.search(r'(?i)\[needs manual review:\s*([^\]]+)\]', entry_text)
            why_manual_review = manual_reason_match.group(1).strip() if manual_reason_match else ""
            updated_entry, fill_report = self._fill_missing_fields_from_validated_metadata(entry_text, validated, entry_metadata, options)
            for field_name in fill_report.get("fields", []):
                enrichment["fields_filled"] += 1
                by_type = enrichment["fields_filled_by_type"]
                by_type[field_name] = int(by_type.get(field_name, 0)) + 1
            autofill_status = str(fill_report.get("autofill_status") or "none")
            if autofill_status == "full":
                enrichment["autofill_full"] += 1
            elif autofill_status == "partial":
                enrichment["autofill_partial"] += 1
            else:
                enrichment["autofill_none"] += 1

            doi = self._normalize_doi_value(str(validated.get("matched_doi") or validated.get("doi") or ""))
            doi_rejected = False
            doi_needs_review = False
            doi_reject_reasons: List[str] = []
            doi_reason_chips: List[str] = []
            resolve_reason_chips: List[str] = list(validated.get("auto_resolve_chips") or [])
            status = str(validated.get("status") or "").strip().lower()
            doi_mode = str(enrichment.get("doi_mode") or "balanced")
            trusted_override = bool((options or {}).get("trusted_verified_doi_override", True))
            if doi:
                if status == "likely_match" and doi_mode == "balanced":
                    doi_needs_review = True
                    enrichment["doi_inserted"] += 1
                    enrichment["doi_needs_review_inserted"] += 1
                    doi_reason_chips = ["mode:balanced", "status:likely_match", "doi:needs_review"]
                else:
                    decision = self._evaluate_doi_alignment(entry_metadata, validated, strict_mode=enrichment["strict_doi_mode"])
                    doi_reason_chips = list(decision.get("chips") or [])
                    if not bool(decision.get("allow")):
                        doi_reject_reasons = [str(x) for x in (decision.get("reasons") or [])]
                        source_name = str(validated.get("source") or "").strip().lower()
                        source_url_value = self._normalize_source_url_value(
                            str(validated.get("matched_source_url") or validated.get("source_url") or "")
                        )
                        # Override for trusted verified DOI sources (e.g., Crossref DOI URL),
                        # so [21]-type cases are inserted instead of rejected.
                        can_override = (
                            trusted_override
                            and status == "verified"
                            and source_name in {"crossref", "openalex", "serper"}
                            and bool(source_url_value)
                            and "doi.org/" in source_url_value.lower()
                        )
                        if can_override:
                            enrichment["doi_inserted"] += 1
                            enrichment["doi_override_inserted"] += 1
                            doi_reason_chips.extend(["override:trusted_verified_source", f"override_source:{source_name}"])
                        else:
                            doi_reason_chips.extend([f"blocked:{r}" for r in doi_reject_reasons[:3]])
                            enrichment["doi_rejected"] += 1
                            enrichment["rejected_numbers"].append(number)
                            doi = ""
                            doi_rejected = True
                    else:
                        enrichment["doi_inserted"] += 1
                if status != "likely_match" and not doi_rejected and not doi_needs_review and not doi_reason_chips:
                    doi_reason_chips = ["doi:inserted"]
                if status == "likely_match" and doi_mode != "balanced":
                    doi_reject_reasons = ["likely_match_requires_balanced_mode"]
                    doi_reason_chips = ["blocked:likely_match_requires_balanced_mode"]
                    enrichment["doi_rejected"] += 1
                    enrichment["rejected_numbers"].append(number)
                    doi = ""
                    doi_rejected = True
            source_url = self._normalize_source_url_value(
                str(validated.get("matched_source_url") or validated.get("source_url") or "")
            )
            if doi_rejected:
                source_url = ""
            updated_entry = self._append_reference_identifiers(
                updated_entry,
                doi=doi,
                source_url=source_url,
                doi_needs_review=doi_needs_review,
            )
            output.append(f"{prefix}{updated_entry}")
            unresolved_after = (
                autofill_status != "full"
                or doi_rejected
                or doi_needs_review
                or status in {"likely_match"}
            )
            if unresolved_after:
                enrichment["still_unresolved"] += 1
            confidence = str(validated.get("status") or "").strip().lower()
            if confidence == "verified":
                confidence = "verified"
            elif confidence == "likely_match":
                confidence = "likely"
            else:
                confidence = "needs_review"
            fixability = self._classify_unresolved_fixability(
                status=status,
                autofill_status=autofill_status,
                why_manual_review=why_manual_review,
                doi_rejected=doi_rejected,
                doi_needs_review=doi_needs_review,
            )
            enrichment["trail"].append({
                "number": number,
                "source_type": str(entry_metadata.get("source_type") or "generic"),
                "source": str(validated.get("source") or ""),
                "confidence": confidence,
                "fields_filled": fill_report.get("fields", []),
                "autofill_status": autofill_status,
                "autofill_expected_fields": fill_report.get("expected_fields", []),
                "autofill_chips": fill_report.get("autofill_chips", []),
                "auto_resolved": bool(validated.get("auto_resolved")),
                "confidence_rejected": bool(validated.get("confidence_rejected")),
                "auto_resolve_chips": resolve_reason_chips,
                "doi_inserted": bool(doi),
                "doi_needs_review": doi_needs_review,
                "doi_rejected": doi_rejected,
                "doi_reject_reasons": doi_reject_reasons,
                "doi_reason_chips": doi_reason_chips,
                "why_manual_review": why_manual_review,
                "fixability": fixability,
            })

        if isinstance(citation_report, dict):
            citation_report["online_validation"] = online
        return '\n'.join(output)

    def _classify_unresolved_fixability(
        self,
        status: str,
        autofill_status: str,
        why_manual_review: str,
        doi_rejected: bool,
        doi_needs_review: bool,
    ) -> str:
        """Classify unresolved references for UI/action targeting."""
        status_value = str(status or "").strip().lower()
        auto_value = str(autofill_status or "").strip().lower()
        reason_value = str(why_manual_review or "").strip().lower()
        if auto_value in {"partial"} or doi_needs_review or status_value in {"likely_match"}:
            return "auto-fixable"
        if status_value in {"not_found", "error"}:
            return "needs-source"
        if doi_rejected and "low" in reason_value:
            return "needs-source"
        return "needs-human-judgment"

    def _fill_missing_fields_from_validated_metadata(
        self,
        entry_text: str,
        validated: Dict[str, Any],
        metadata: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Fill explicit [field missing] placeholders from high-confidence metadata.

        Safety rule: fill-only-missing. Existing non-placeholder user text is never overwritten.
        """
        entry = str(entry_text or "")
        status = str(validated.get("status") or "").strip().lower()
        score = float(validated.get("score") or 0.0)
        absolute_enforcement = bool((options or {}).get("absolute_verified_doi_enforcement", True))
        require_verified_doi = bool((options or {}).get("verified_doi_autocomplete", True))
        doi_value = self._normalize_doi_value(str(validated.get("matched_doi") or validated.get("doi") or ""))
        if status != "verified":
            return entry, {"fields": [], "expected_fields": [], "autofill_status": "none", "autofill_chips": ["autofill:none", "reason:untrusted_source"]}
        if require_verified_doi and not doi_value:
            return entry, {"fields": [], "expected_fields": [], "autofill_status": "none", "autofill_chips": ["autofill:none", "reason:verified_doi_required"]}
        if not absolute_enforcement and ("score" in validated and score < 0.88):
            return entry, {"fields": [], "expected_fields": [], "autofill_status": "none", "autofill_chips": ["autofill:none", "reason:score_below_fill_threshold"]}

        enriched = self._enrich_validated_metadata_from_doi(validated)
        updates = {
            "title": str(enriched.get("matched_title") or "").strip().rstrip("."),
            "journal": str(enriched.get("matched_journal") or enriched.get("matched_container_title") or "").strip().rstrip("."),
            "year": self._extract_year_token(str(enriched.get("matched_year") or "")),
            "volume": str(enriched.get("matched_volume") or "").strip(),
            "page": str(enriched.get("matched_pages") or "").strip(),
            "place": str(enriched.get("matched_place") or "").strip().rstrip("."),
            "publisher": str(enriched.get("matched_publisher") or "").strip().rstrip("."),
            "editor": str(enriched.get("matched_editor") or "").strip().rstrip("."),
            "url": str(enriched.get("matched_source_url") or "").strip(),
        }
        replacement_map = {
            "title": "[title missing]",
            "journal": "[journal missing]",
            "year": "[year missing]",
            "volume": "[volume missing]",
            "page": "[page missing]",
            "place": "[place missing]",
            "publisher": "[publisher missing]",
            "editor": "[editor missing]",
            "url": "[url missing]",
        }

        filled: List[str] = []
        expected: List[str] = []
        result = entry
        for field_name, placeholder in replacement_map.items():
            if re.search(re.escape(placeholder), result, flags=re.IGNORECASE):
                expected.append(field_name)
            value = updates.get(field_name, "")
            if not value:
                continue
            next_result, changed = self._replace_missing_placeholder(result, placeholder, value)
            if changed:
                result = next_result
                filled.append(field_name)
        expected_unique = list(dict.fromkeys(expected))
        if len(expected_unique) == 0:
            status_label = "none"
        elif len(filled) >= len(expected_unique):
            status_label = "full"
        elif len(filled) > 0:
            status_label = "partial"
        else:
            status_label = "none"
        chips = [f"autofill:{status_label}"]
        if expected_unique:
            chips.append(f"expected:{len(expected_unique)}")
        if filled:
            chips.append(f"filled:{len(filled)}")
        if expected_unique and len(filled) < len(expected_unique):
            missing_left = len(expected_unique) - len(filled)
            chips.append(f"remaining:{missing_left}")
        return result, {"fields": filled, "expected_fields": expected_unique, "autofill_status": status_label, "autofill_chips": chips}

    def _enrich_validated_metadata_from_doi(self, validated: Dict[str, Any]) -> Dict[str, Any]:
        """Best-effort DOI second pass to maximize missing-field completion."""
        result = dict(validated or {})
        doi_value = self._normalize_doi_value(str(result.get("matched_doi") or result.get("doi") or ""))
        if not doi_value:
            return result
        try:
            crossref = self._fetch_crossref_work_by_doi(doi_value)
            if not isinstance(crossref, dict):
                return result
            mapping = {
                "matched_title": str(crossref.get("title") or ""),
                "matched_journal": str(crossref.get("journal") or ""),
                "matched_container_title": str(crossref.get("container_title") or ""),
                "matched_year": str(crossref.get("year") or ""),
                "matched_pages": str(crossref.get("pages") or ""),
                "matched_volume": str(crossref.get("volume") or ""),
                "matched_issue": str(crossref.get("issue") or ""),
                "matched_place": str(crossref.get("place") or ""),
                "matched_publisher": str(crossref.get("publisher") or ""),
                "matched_editor": str(crossref.get("editor") or ""),
                "matched_source_url": str(crossref.get("source_url") or ""),
                "matched_first_author": str(crossref.get("first_author") or ""),
            }
            for key, value in mapping.items():
                if value and not str(result.get(key) or "").strip():
                    result[key] = value
        except Exception:
            return result
        return result

    def _replace_missing_placeholder(self, text: str, placeholder: str, value: str) -> Tuple[str, bool]:
        """Replace a single placeholder token case-insensitively."""
        pattern = re.compile(re.escape(placeholder), flags=re.IGNORECASE)
        if not pattern.search(text or ""):
            return text, False
        return pattern.sub(str(value).strip(), text, count=1), True

    def _extract_year_token(self, value: str) -> str:
        """Return normalized 4-digit year token when present."""
        match = re.search(r"\b((?:19|20)\d{2})\b", str(value or ""))
        return match.group(1) if match else ""

    def _allow_doi_insert(self, reference_metadata: Dict[str, Any], validated: Dict[str, Any], strict_mode: bool = True) -> bool:
        """Allow DOI insertion only when metadata alignment is strong."""
        decision = self._evaluate_doi_alignment(reference_metadata, validated, strict_mode=strict_mode)
        return bool(decision.get("allow"))

    def _evaluate_doi_alignment(self, reference_metadata: Dict[str, Any], validated: Dict[str, Any], strict_mode: bool = True) -> Dict[str, Any]:
        """Return explicit DOI insertion decision with threshold diagnostics."""
        status = str(validated.get("status") or "").strip().lower()
        score = float(validated.get("score") or 1.0)
        min_score = 0.93 if strict_mode else 0.86
        min_title_similarity = 0.90 if strict_mode else 0.80
        reasons: List[str] = []
        chips: List[str] = []

        if status != "verified":
            reasons.append("status_not_verified")
        else:
            chips.append("status:verified")
        if score < min_score:
            reasons.append(f"score_below_threshold({score:.2f}<{min_score:.2f})")
        else:
            chips.append(f"score:{score:.2f}")

        # Backward-compatible path: if this validated payload only carries DOI
        # (without matching metadata fields), trust verified status + score.
        if not any([
            str(validated.get("matched_title") or "").strip(),
            str(validated.get("matched_year") or "").strip(),
            str(validated.get("matched_pages") or "").strip(),
            str(validated.get("matched_first_author") or "").strip(),
        ]):
            allow = not reasons
            if allow:
                chips.append("fallback:doi_only_payload")
            return {"allow": allow, "reasons": reasons, "chips": chips, "thresholds": {"score": min_score, "title_similarity": min_title_similarity}}

        title_similarity = self._text_similarity(
            str(reference_metadata.get("title") or ""),
            str(validated.get("matched_title") or ""),
        )
        if title_similarity < min_title_similarity:
            reasons.append(f"title_similarity_below_threshold({title_similarity:.2f}<{min_title_similarity:.2f})")
        else:
            chips.append(f"title:{title_similarity:.2f}")

        ref_year = self._extract_year_token(str(reference_metadata.get("year") or ""))
        matched_year = self._extract_year_token(str(validated.get("matched_year") or ""))
        if ref_year and matched_year and ref_year != matched_year:
            # Allow online-first/pub-ahead drift of one year.
            try:
                if abs(int(ref_year) - int(matched_year)) > 1:
                    reasons.append(f"year_mismatch({ref_year}!={matched_year})")
                else:
                    chips.append(f"year:near({ref_year}/{matched_year})")
            except Exception:
                reasons.append(f"year_mismatch({ref_year}!={matched_year})")
        elif ref_year and matched_year:
            chips.append(f"year:{ref_year}")

        ref_author = self._extract_reference_first_author(str(reference_metadata.get("authors") or ""))
        matched_author = self._extract_reference_first_author(str(validated.get("matched_first_author") or ""))
        if ref_author and matched_author:
            if ref_author == matched_author:
                chips.append("author:first_match")
            elif strict_mode:
                reasons.append(f"first_author_mismatch({ref_author}!={matched_author})")
            else:
                chips.append("author:soft_mismatch")

        ref_pages = str(reference_metadata.get("pages") or "").strip()
        matched_pages = str(validated.get("matched_pages") or "").strip()
        if ref_pages and matched_pages and not self._page_tokens_match(ref_pages, matched_pages):
            reasons.append("pages_mismatch")
        elif ref_pages and matched_pages:
            chips.append("pages:match")

        allow = len(reasons) == 0
        return {
            "allow": allow,
            "reasons": reasons,
            "chips": chips,
            "thresholds": {
                "score": min_score,
                "title_similarity": min_title_similarity,
            },
        }

    def _append_reference_identifiers(self, entry_text: str, doi: str = "", source_url: str = "", doi_needs_review: bool = False) -> str:
        """Append reference identifiers without duplication.

        Policy: prefer DOI when available; append source URL only when DOI is absent.
        """
        entry = str(entry_text or "").strip()
        if not entry:
            return entry

        normalized_entry = self._normalize_match_text(entry)
        needs_doi = bool(doi) and self._normalize_match_text(doi) not in normalized_entry
        # Keep references concise for journal workflows:
        # if a DOI is available, do not append an additional source URL.
        needs_source = (not needs_doi) and bool(source_url) and source_url.lower() not in entry.lower()

        if not (needs_doi or needs_source):
            return entry

        base = entry.rstrip()
        if base and base[-1] not in ".!?":
            base += "."

        if needs_doi:
            if doi_needs_review:
                base += f" doi: {doi} [needs review]."
            else:
                base += f" doi: {doi}."
        if needs_source:
            base += f" Available from: {source_url}."
        return base

    def _normalize_doi_value(self, value: str) -> str:
        """Normalize DOI token to canonical value without URL prefix."""
        text = str(value or "").strip()
        if not text:
            return ""
        text = re.sub(r'(?i)^https?://(?:dx\.)?doi\.org/', '', text)
        text = re.sub(r'(?i)^doi:\s*', '', text)
        text = text.strip().rstrip(".,;")
        if not re.match(r'^10\.\d{4,9}/\S+$', text, flags=re.IGNORECASE):
            return ""
        return text

    def _normalize_source_url_value(self, value: str) -> str:
        """Return a safe source URL candidate for reference tail append."""
        text = str(value or "").strip().rstrip(".,;")
        if not text:
            return ""
        if not re.match(r'(?i)^https?://', text):
            return ""
        return text

    def build_reference_profile_report(self, text: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        """Return profile details + profile-aware validation messages."""
        profile = self.resolve_journal_profile(options)
        entries = self._extract_reference_entries(text)
        issues: Dict[str, int] = {}

        def bump(code: str):
            issues[code] = int(issues.get(code, 0)) + 1

        for entry in entries:
            metadata = self._analyze_reference_entry(entry)
            authors = str(metadata.get("authors") or "")
            title = str(metadata.get("title") or "")
            journal = str(metadata.get("journal") or "")
            initials_with_periods = bool(profile.get("initials_with_periods"))
            if initials_with_periods:
                if re.search(r'\b[A-Z]{2,}\b', authors):
                    bump("initials_missing_periods")
            else:
                if re.search(r'\b[A-Z]\.', authors):
                    bump("initials_have_periods")

            title_mode = str(profile.get("title_case", "sentence")).strip().lower()
            alpha_words = re.findall(r"[A-Za-z][A-Za-z'’\-]*", title)
            if title_mode == "sentence" and len(alpha_words) >= 3:
                extra_caps = 0
                for word in alpha_words[1:]:
                    if (
                        word[:1].isupper() and
                        word.lower() not in self.TITLE_PROPER_WORDS and
                        word not in self.TITLE_ACRONYMS
                    ):
                        extra_caps += 1
                if extra_caps >= 2:
                    bump("title_not_sentence_case")
            if title_mode == "title" and len(alpha_words) >= 3:
                non_small_lower = 0
                for word in alpha_words[1:]:
                    if word.lower() in self.TITLE_SMALL_WORDS:
                        continue
                    if word.islower():
                        non_small_lower += 1
                if non_small_lower >= 2:
                    bump("title_not_title_case")

            if str(metadata.get("source_type") or "") == "journal":
                journal_mode = str(profile.get("journal_abbrev", "nlm")).strip().lower()
                if journal_mode == "nlm":
                    if re.search(r'\b(?:journal of|international|proceedings of)\b', journal, flags=re.IGNORECASE):
                        bump("journal_not_abbreviated")
                else:
                    if re.search(r'\b(?:J|Int|Archit|Res|Sci|Rev|Clin|Med|Technol|Environ|Assoc)\b', journal):
                        bump("journal_looks_abbreviated")

        message_map = {
            "initials_missing_periods": "author initials should use periods (A.B.)",
            "initials_have_periods": "author initials should omit periods (AB)",
            "title_not_sentence_case": "reference titles should be in sentence case",
            "title_not_title_case": "reference titles should be in title case",
            "journal_not_abbreviated": "journal names should use NLM-style abbreviations",
            "journal_looks_abbreviated": "journal names should be full (not abbreviated)",
        }
        ordered_codes = sorted(issues.keys(), key=lambda key: (-issues[key], key))
        validation_messages = [
            f"{issues[code]} reference(s): {message_map.get(code, code)}"
            for code in ordered_codes
        ]

        return {
            "profile_id": str(profile.get("id", "vancouver_periods")),
            "profile_label": str(profile.get("label", "Vancouver")),
            "rules": {
                "initials": "with periods (A.B.)" if bool(profile.get("initials_with_periods")) else "without periods (AB)",
                "title_case": str(profile.get("title_case", "sentence")),
                "journal_names": "NLM abbreviations" if str(profile.get("journal_abbrev", "nlm")) == "nlm" else "full journal names",
            },
            "reference_count": len(entries),
            "issue_counts": issues,
            "validation_messages": validation_messages[:8],
        }

    def _split_non_reference_and_reference_lines(self, text: str) -> Tuple[List[str], List[str]]:
        """Split manuscript lines into non-reference body and references section lines."""
        source_lines = (text or "").split('\n')
        body_lines: List[str] = []
        reference_lines: List[str] = []
        in_references = False

        heading_re = re.compile(r'^\s*references?\s*:?\s*$', flags=re.IGNORECASE)
        section_break_re = re.compile(
            r'^\s*(?:appendix|acknowledg(?:e)?ments?|funding|conflicts?\s+of\s+interest|author\s+contributions?)\s*:?\s*$',
            flags=re.IGNORECASE
        )

        for line in source_lines:
            if heading_re.match(line):
                in_references = True
                reference_lines.append(line)
                continue
            if in_references and section_break_re.match(line):
                in_references = False
                body_lines.append(line)
                continue
            if in_references:
                reference_lines.append(line)
            else:
                body_lines.append(line)

        return body_lines, reference_lines

    def _extract_citation_numbers_in_order(self, text: str) -> List[int]:
        """Return unique citation numbers in the order they first appear in body text."""
        body_lines, _ = self._split_non_reference_and_reference_lines(text or "")
        ordered: List[int] = []
        seen = set()

        for line in body_lines:
            for match in re.finditer(r'\[(.*?)\]', line):
                content = (match.group(1) or "").strip()
                if not re.fullmatch(r'\d+(?:\s*,\s*\d+)*', content):
                    continue
                for part in content.split(','):
                    number = int(part.strip())
                    if number in seen:
                        continue
                    seen.add(number)
                    ordered.append(number)

        return ordered

    def _extract_reference_numbered_entries(self, text: str) -> List[Dict[str, Any]]:
        """Extract reference entries with optional explicit numeric index."""
        lines = (text or "").split('\n')
        entries: List[Dict[str, Any]] = []
        in_references = False
        current_index = -1
        auto_number = 1

        heading_re = re.compile(r'^\s*references?\s*:?\s*$', flags=re.IGNORECASE)
        leading_marker_re = re.compile(r'^\s*(?:\[\s*(\d+)\s*\]|(\d+)\s*[.)])\s*')
        section_break_re = re.compile(
            r'^\s*(?:appendix|acknowledg(?:e)?ments?|funding|conflicts?\s+of\s+interest|author\s+contributions?)\s*:?\s*$',
            flags=re.IGNORECASE
        )
        continuation_re = re.compile(
            r'^(?:https?://|www\.|doi:\s*10\.|10\.\d{4,9}/|available\s+from|accessed\b|pmid\b|pmcid\b|epub\b)',
            flags=re.IGNORECASE
        )

        for line in lines:
            if heading_re.match(line):
                in_references = True
                current_index = -1
                auto_number = 1
                continue

            if in_references and section_break_re.match(line):
                in_references = False
                current_index = -1
                continue

            if not in_references:
                continue

            stripped = line.strip()
            if not stripped:
                current_index = -1
                continue

            marker_match = leading_marker_re.match(stripped)
            cleaned = leading_marker_re.sub('', stripped)
            marker_number: Optional[int] = None
            if marker_match:
                marker_number = int(marker_match.group(1) or marker_match.group(2))

            is_continuation = (
                current_index >= 0 and
                marker_match is None and
                (
                    line[:1].isspace() or
                    continuation_re.match(cleaned) is not None
                )
            )
            if is_continuation:
                entries[current_index]["entry"] = entries[current_index]["entry"].rstrip() + ' ' + cleaned
                continue

            if marker_number is None:
                marker_number = auto_number
            auto_number = max(auto_number, marker_number + 1)

            entries.append({
                "number": marker_number,
                "entry": cleaned,
            })
            current_index = len(entries) - 1

        return entries

    def _build_vancouver_renumber_plan(self, text: str) -> Tuple[Dict[int, int], List[Dict[str, Any]]]:
        """Build first-appearance citation remap plus ordered reference entries."""
        extracted = self._extract_reference_numbered_entries(text or "")
        indexed_entries: List[Dict[str, Any]] = []
        entries_by_number: Dict[int, List[Dict[str, Any]]] = {}

        for idx, item in enumerate(extracted):
            entry = {
                "source_index": idx,
                "number": int(item.get("number") or 0),
                "entry": str(item.get("entry") or ""),
            }
            indexed_entries.append(entry)
            entries_by_number.setdefault(entry["number"], []).append(entry)

        ordered_entries: List[Dict[str, Any]] = []
        used_source_indexes = set()
        renumber_map: Dict[int, int] = {}

        for old_number in self._extract_citation_numbers_in_order(text or ""):
            for entry in entries_by_number.get(old_number, []):
                source_index = int(entry["source_index"])
                if source_index in used_source_indexes:
                    continue
                used_source_indexes.add(source_index)
                ordered_entries.append(entry)
                renumber_map[old_number] = len(ordered_entries)
                break

        for entry in indexed_entries:
            source_index = int(entry["source_index"])
            if source_index in used_source_indexes:
                continue
            used_source_indexes.add(source_index)
            ordered_entries.append(entry)
            old_number = int(entry["number"])
            if old_number not in renumber_map:
                renumber_map[old_number] = len(ordered_entries)

        return renumber_map, ordered_entries

    def _renumber_citation_blocks(self, text: str, renumber_map: Dict[int, int]) -> str:
        """Renumber numeric body citations with a first-appearance map."""
        if not renumber_map:
            return text

        def repl(match):
            content = (match.group(1) or "").strip()
            if not re.fullmatch(r'\d+(?:\s*,\s*\d+)*', content):
                return match.group(0)

            renumbered: List[str] = []
            for part in content.split(','):
                old_number = int(part.strip())
                renumbered.append(str(int(renumber_map.get(old_number, old_number))))
            return '[' + ', '.join(renumbered) + ']'

        return re.sub(r'\[(.*?)\]', repl, text)

    def build_citation_reference_validator_report(self, text: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        """Validate citation/reference integrity with issue categories and counts."""
        body_lines, _ = self._split_non_reference_and_reference_lines(text or "")
        body_text = "\n".join(body_lines)
        ref_entries = self._extract_reference_numbered_entries(text or "")

        issue_counts: Dict[str, int] = {}
        details: Dict[str, Any] = {
            "citation_numbers_missing_references": [],
            "reference_numbers_uncited": [],
            "reference_missing_author_numbers": [],
            "reference_missing_title_numbers": [],
            "reference_missing_journal_numbers": [],
            "reference_missing_year_numbers": [],
            "reference_missing_volume_numbers": [],
            "reference_missing_pages_numbers": [],
            "reference_missing_place_numbers": [],
            "reference_missing_publisher_numbers": [],
            "reference_missing_editor_numbers": [],
            "reference_missing_cited_date_numbers": [],
            "reference_missing_url_numbers": [],
            "source_type_numbers": {
                "journal": [],
                "proceedings": [],
                "book": [],
                "chapter": [],
                "website": [],
                "generic": [],
            },
        }

        def bump(code: str, amount: int = 1):
            issue_counts[code] = int(issue_counts.get(code, 0)) + int(amount)

        # Malformed bracket syntax checks.
        open_count = body_text.count('[')
        close_count = body_text.count(']')
        if open_count > close_count:
            bump("malformed_bracket_unclosed", open_count - close_count)
        elif close_count > open_count:
            bump("malformed_bracket_unopened", close_count - open_count)

        # Numeric citation block parsing.
        citation_block_count = 0
        cited_numbers: List[int] = []
        duplicate_within_block_count = 0
        malformed_citation_block_count = 0

        for line in body_lines:
            for match in re.finditer(r'\[(.*?)\]', line):
                content = (match.group(1) or "").strip()
                if not content:
                    malformed_citation_block_count += 1
                    continue

                citation_block_count += 1
                if not re.fullmatch(r'\d+(?:\s*,\s*\d+)*', content):
                    malformed_citation_block_count += 1
                    continue

                values = [int(part.strip()) for part in content.split(',') if part.strip()]
                seen: Set[int] = set()
                duplicated = False
                for value in values:
                    cited_numbers.append(value)
                    if value in seen:
                        duplicated = True
                    seen.add(value)
                if duplicated:
                    duplicate_within_block_count += 1

        if malformed_citation_block_count > 0:
            bump("malformed_citation_block", malformed_citation_block_count)
        if duplicate_within_block_count > 0:
            bump("duplicate_citation_numbers_in_block", duplicate_within_block_count)

        cited_set = set(cited_numbers)
        reference_numbers = {int(item["number"]) for item in ref_entries if isinstance(item.get("number"), int)}

        missing_refs = sorted(number for number in cited_set if number not in reference_numbers)
        if missing_refs:
            bump("citation_missing_reference", len(missing_refs))
            details["citation_numbers_missing_references"] = missing_refs

        uncited_refs = sorted(number for number in reference_numbers if number not in cited_set)
        if uncited_refs:
            bump("reference_not_cited_in_text", len(uncited_refs))
            details["reference_numbers_uncited"] = uncited_refs

        # Reference field completeness checks by source type.
        missing_by_code: Dict[str, List[int]] = {
            "reference_missing_author": [],
            "reference_missing_title": [],
            "reference_missing_journal": [],
            "reference_missing_year": [],
            "reference_missing_volume": [],
            "reference_missing_pages": [],
            "reference_missing_place": [],
            "reference_missing_publisher": [],
            "reference_missing_editor": [],
            "reference_missing_cited_date": [],
            "reference_missing_url": [],
        }
        detail_key_by_code = {
            "reference_missing_author": "reference_missing_author_numbers",
            "reference_missing_title": "reference_missing_title_numbers",
            "reference_missing_journal": "reference_missing_journal_numbers",
            "reference_missing_year": "reference_missing_year_numbers",
            "reference_missing_volume": "reference_missing_volume_numbers",
            "reference_missing_pages": "reference_missing_pages_numbers",
            "reference_missing_place": "reference_missing_place_numbers",
            "reference_missing_publisher": "reference_missing_publisher_numbers",
            "reference_missing_editor": "reference_missing_editor_numbers",
            "reference_missing_cited_date": "reference_missing_cited_date_numbers",
            "reference_missing_url": "reference_missing_url_numbers",
        }

        for item in ref_entries:
            number = int(item.get("number") or 0)
            entry = str(item.get("entry") or "")
            if not entry.strip():
                continue
            metadata = self._analyze_reference_entry(entry)
            source_type = str(metadata.get("source_type") or "generic")
            if source_type not in details["source_type_numbers"]:
                source_type = "generic"
            details["source_type_numbers"][source_type].append(number)
            for spec in self._reference_missing_specs(metadata):
                missing_by_code[str(spec["code"])].append(number)

        gate_summary: Dict[str, Any] = {
            "total": 0,
            "passed": 0,
            "auto_repaired": 0,
            "failed": 0,
            "needs_manual_review_numbers": [],
            "reasons_by_number": {},
            "templates": self._reference_shape_templates(),
        }
        for item in ref_entries:
            number = int(item.get("number") or 0)
            entry = str(item.get("entry") or "")
            if number <= 0 or not entry.strip():
                continue
            metadata = self._analyze_reference_entry(entry)
            gate_summary["total"] += 1
            result = self._finalize_reference_shape(entry, metadata, {})
            if bool(result.get("passed")):
                gate_summary["passed"] += 1
                if bool(result.get("repaired")):
                    gate_summary["auto_repaired"] += 1
                continue
            gate_summary["failed"] += 1
            gate_summary["needs_manual_review_numbers"].append(number)
            reasons = result.get("reasons") if isinstance(result.get("reasons"), list) else []
            gate_summary["reasons_by_number"][str(number)] = [str(reason) for reason in reasons[:3]]
        details["reference_quality_gate"] = gate_summary

        for code, numbers in missing_by_code.items():
            if numbers:
                bump(code, len(numbers))
                details[detail_key_by_code[code]] = numbers

        message_map = {
            "malformed_bracket_unclosed": "unclosed '[' bracket(s) in body text",
            "malformed_bracket_unopened": "unopened ']' bracket(s) in body text",
            "malformed_citation_block": "malformed in-text citation block(s) (expected [1] or [1, 2])",
            "duplicate_citation_numbers_in_block": "citation block(s) contain duplicate numbers (for example [2, 2])",
            "citation_missing_reference": "citation number(s) have no matching reference entry",
            "reference_not_cited_in_text": "reference entry number(s) are not cited in body text",
            "reference_missing_author": "reference entry/entries missing author or organization",
            "reference_missing_title": "reference entry/entries missing title",
            "reference_missing_journal": "journal article entry/entries missing journal name",
            "reference_missing_year": "reference entry/entries missing year pattern",
            "reference_missing_volume": "journal article entry/entries missing volume pattern",
            "reference_missing_pages": "reference entry/entries missing page range",
            "reference_missing_place": "book/website entry/entries missing place of publication",
            "reference_missing_publisher": "book/website entry/entries missing publisher",
            "reference_missing_editor": "chapter entry/entries missing editor",
            "reference_missing_cited_date": "website entry/entries missing cited date",
            "reference_missing_url": "website entry/entries missing URL",
            "reference_final_shape_failed": "reference entry/entries need manual review after final-shape validation",
        }
        ordered_codes = sorted(issue_counts.keys(), key=lambda key: (-issue_counts[key], key))
        messages = [
            f"{issue_counts[code]} issue(s): {message_map.get(code, code)}"
            for code in ordered_codes
        ]

        citation_issue_codes = {
            "malformed_bracket_unclosed",
            "malformed_bracket_unopened",
            "malformed_citation_block",
            "duplicate_citation_numbers_in_block",
            "citation_missing_reference",
            "reference_not_cited_in_text",
        }
        citation_issue_total = sum(count for code, count in issue_counts.items() if code in citation_issue_codes)
        reference_issue_total = sum(count for code, count in issue_counts.items() if code not in citation_issue_codes)
        online_validation = self._build_online_reference_validation_report(ref_entries, options or {})
        book_numbers = details.get("source_type_numbers", {}).get("book", [])
        book_issue_codes = {"reference_missing_author", "reference_missing_title", "reference_missing_place", "reference_missing_publisher", "reference_missing_year"}
        book_issues = sum(int(issue_counts.get(code, 0)) for code in book_issue_codes)
        details["book_validation"] = {
            "total_books": len(book_numbers),
            "passed": bool(len(book_numbers) > 0 and book_issues == 0),
            "failed": bool(len(book_numbers) > 0 and book_issues > 0),
            "issues": book_issues,
        }
        if int(gate_summary.get("failed", 0)) > 0:
            bump("reference_final_shape_failed", int(gate_summary.get("failed", 0)))
            details["reference_final_shape_failed_numbers"] = list(gate_summary.get("needs_manual_review_numbers", []))

        return {
            "summary": {
                "total_issues": sum(issue_counts.values()),
                "citation_issues": citation_issue_total,
                "reference_issues": reference_issue_total,
                "citation_blocks": citation_block_count,
                "unique_citations": len(cited_set),
                "references": len(ref_entries),
            },
            "category_counts": issue_counts,
            "messages": messages[:12],
            "details": details,
            "online_validation": online_validation,
        }

    def _build_online_reference_validation_report(
        self,
        ref_entries: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Validate references against public metadata services when enabled."""
        enabled = bool((options or {}).get("online_reference_validation", False))
        serper_requested = bool((options or {}).get("online_reference_serper_fallback", True))
        serper_available = bool(self._get_serper_api_key())
        serper_enabled = bool(serper_requested and serper_available)
        admin_cap = self._resolve_online_validation_admin_cap(options)
        total_detected_references = len(ref_entries)
        effective_limit = min(total_detected_references, admin_cap)
        self._reset_online_lookup_metrics()
        summary = {
            "checked": 0,
            "attempted": 0,
            "verified": 0,
            "likely_match": 0,
            "mismatch": 0,
            "not_found": 0,
            "ambiguous": 0,
            "skipped": 0,
            "error": 0,
        }
        report = {
            "enabled": enabled,
            "serper_enabled": serper_enabled,
            "serper_requested": serper_requested,
            "serper_available": serper_available,
            "limit": effective_limit,
            "admin_cap": admin_cap,
            "total_detected_references": total_detected_references,
            "effective_limit": effective_limit,
            "summary": summary,
            "entries": [],
            "messages": [],
            "lookup_metrics": self._online_lookup_metrics,
        }
        if not enabled:
            report["messages"] = ["Online reference validation was disabled for this run."]
            self._publish_online_lookup_metrics()
            return report

        checked = 0
        for item in ref_entries:
            if checked >= effective_limit:
                summary["skipped"] += 1
                continue

            number = int(item.get("number") or 0)
            entry = str(item.get("entry") or "").strip()
            if not entry:
                continue
            metadata = self._analyze_reference_entry(entry)
            if not metadata.get("has_title"):
                summary["skipped"] += 1
                report["entries"].append({
                    "number": number,
                    "status": "skipped",
                    "reason": "Reference title is missing, so no reliable online lookup was attempted.",
                    "entry": entry,
                })
                continue

            checked += 1
            result = self._validate_reference_online(number, entry, metadata, allow_serper=serper_enabled, options=options)
            summary["checked"] += 1
            status = str(result.get("status") or "error")
            if status != "skipped":
                summary["attempted"] += 1
            summary[status] = int(summary.get(status, 0)) + 1
            report["entries"].append(result)

        if checked >= effective_limit and total_detected_references > effective_limit:
            report["messages"].append(
                f"Online validation checked the first {effective_limit} references (cap={admin_cap}) to keep processing responsive."
            )
        if summary["error"] > 0:
            report["messages"].append("Some reference lookups failed due to remote API/network errors.")
        if summary["not_found"] > 0 or summary["mismatch"] > 0 or summary["ambiguous"] > 0:
            report["messages"].append("Review references marked not found, mismatch, or ambiguous before final submission.")
        if summary["attempted"] == 0:
            report["messages"].append("No eligible references were available for online validation.")
        if serper_requested and not serper_available:
            report["messages"].append("SERPER_API_KEY not set; Serper fallback remained disabled.")
        if not serper_requested:
            report["messages"].append("Serper fallback is disabled by runtime settings.")
        self._publish_online_lookup_metrics()
        return report

    def _resolve_online_validation_admin_cap(self, options: Optional[Dict[str, Any]]) -> int:
        """Resolve runtime-configurable online validation cap with safe bounds."""
        raw_value = self.ONLINE_VALIDATION_ADMIN_CAP_DEFAULT
        if isinstance(options, dict):
            raw_value = options.get("online_reference_validation_admin_cap", raw_value)
        try:
            parsed = int(raw_value)
        except Exception:
            parsed = self.ONLINE_VALIDATION_ADMIN_CAP_DEFAULT
        return max(1, min(500, parsed))

    def _get_serper_api_key(self) -> str:
        """Return Serper API key from environment."""
        return str(os.getenv("SERPER_API_KEY", "") or "").strip()

    def _cache_get(self, key: str) -> Optional[Any]:
        """Get a non-expired cached online validation payload."""
        if not key:
            return None
        now = time.time()
        with self._online_validation_cache_lock:
            cached = self._online_validation_cache.get(key)
        if not cached:
            self._increment_online_lookup_metric("cache_misses")
            return None
        expires_at = float(cached.get("expires_at") or 0)
        if expires_at <= now:
            with self._online_validation_cache_lock:
                self._online_validation_cache.pop(key, None)
            self._increment_online_lookup_metric("cache_misses")
            return None
        self._increment_online_lookup_metric("cache_hits")
        return copy.deepcopy(cached.get("value"))

    def _cache_set(self, key: str, value: Any):
        """Store one online validation payload in bounded in-memory cache."""
        if not key:
            return
        now = time.time()
        with self._online_validation_cache_lock:
            self._online_validation_cache[key] = {
                "expires_at": now + self.ONLINE_VALIDATION_CACHE_TTL_SECONDS,
                "value": copy.deepcopy(value),
            }
            if len(self._online_validation_cache) <= self.ONLINE_VALIDATION_CACHE_MAX_ENTRIES:
                return
            # Drop the oldest-expiring keys first to keep cache bounded.
            stale_first = sorted(
                self._online_validation_cache.items(),
                key=lambda item: float(item[1].get("expires_at") or 0),
            )
            overflow = len(self._online_validation_cache) - self.ONLINE_VALIDATION_CACHE_MAX_ENTRIES
            for idx in range(max(overflow, 0)):
                self._online_validation_cache.pop(stale_first[idx][0], None)

    def _cache_key(self, namespace: str, payload: Dict[str, Any]) -> str:
        """Build a stable cache key for remote lookups."""
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        return f"{namespace}:{raw}"

    def _sanitize_lookup_fragment(self, value: str, max_terms: int) -> str:
        """Remove sensitive/noisy tokens and keep concise lookup-safe terms."""
        text = str(value or "").strip()
        if not text:
            return ""
        # Never send URLs/emails/raw DOI literals to search query text.
        text = re.sub(r'(?i)\b(?:https?|ftp)://\S+', ' ', text)
        text = re.sub(r'(?i)\bwww\.\S+', ' ', text)
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', ' ', text)
        text = re.sub(r'(?i)\bdoi:\s*10\.\d{4,9}/[^\s<>"\']+', ' ', text)
        text = re.sub(r'(?i)\b10\.\d{4,9}/[^\s<>"\']+', ' ', text)

        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", text)
        compact = [token for token in tokens if len(token) >= 2]
        if max_terms > 0:
            compact = compact[:max_terms]
        return " ".join(compact)

    def _build_serper_query(self, metadata: Dict[str, Any]) -> str:
        """Build a redacted references-only search query for Serper."""
        title_part = self._sanitize_lookup_fragment(
            str(metadata.get("title") or ""),
            self.SERPER_MAX_TITLE_TERMS,
        )
        author_part = self._sanitize_lookup_fragment(
            self._extract_reference_first_author(str(metadata.get("authors") or "")),
            1,
        )
        journal_part = self._sanitize_lookup_fragment(
            str(metadata.get("journal") or ""),
            self.SERPER_MAX_JOURNAL_TERMS,
        )
        year_match = re.search(r'\b(?:19|20)\d{2}\b', str(metadata.get("year") or ""))
        year_part = year_match.group(0) if year_match else ""
        parts = [part for part in [title_part, author_part, year_part, journal_part] if part]
        return " ".join(parts).strip()

    def _normalize_serper_candidate(self, item: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Convert one Serper organic result into internal matching metadata."""
        if not isinstance(item, dict):
            return None
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        link = str(item.get("link") or "").strip()
        if not title and not snippet:
            return None

        year_match = re.search(r'\b(?:19|20)\d{2}\b', f"{title} {snippet}")
        doi_match = re.search(r'(?i)\b10\.\d{4,9}/[^\s<>"\')\]]+', f"{title} {snippet} {link}")

        return {
            "source": "serper",
            "title": title or snippet,
            "journal": "",
            "year": year_match.group(0) if year_match else "",
            "pages": "",
            "volume": "",
            "issue": "",
            "place": "",
            "publisher": "",
            "doi": doi_match.group(0).rstrip(".,;") if doi_match else "",
            "source_url": link,
            "first_author": "",
        }

    def _search_serper_works(self, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search Serper using redacted reference metadata when configured."""
        api_key = self._get_serper_api_key()
        if not api_key:
            return []
        query = self._build_serper_query(metadata)
        if not query:
            return []

        key = self._cache_key("serper_search", {"q": query, "num": self.SERPER_RESULTS_LIMIT})
        cached = self._cache_get(key)
        if isinstance(cached, list):
            self._increment_online_lookup_metric("serper_cache_hits")
            return cached

        self._increment_online_lookup_metric("serper_requests")
        response = requests.post(
            self.SERPER_SEARCH_ENDPOINT,
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": self.SERPER_RESULTS_LIMIT},
            timeout=self.ONLINE_VALIDATION_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        organic = payload.get("organic") if isinstance(payload, dict) else []
        normalized: List[Dict[str, Any]] = []
        for item in organic if isinstance(organic, list) else []:
            candidate = self._normalize_serper_candidate(item)
            if candidate:
                normalized.append(candidate)
        self._cache_set(key, normalized)
        return normalized

    def _validate_reference_online(
        self,
        number: int,
        entry: str,
        metadata: Dict[str, Any],
        allow_serper: bool = True,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run conservative online validation for one journal reference."""
        base = {
            "number": number,
            "entry": entry,
            "doi": str(metadata.get("doi") or ""),
            "title": str(metadata.get("title") or ""),
            "year": str(metadata.get("year") or ""),
            "journal": str(metadata.get("journal") or ""),
            "status": "not_found",
            "reason": "No matching record was found online.",
            "source": "",
            "source_url": "",
            "matched_doi": "",
            "matched_source_url": "",
        }

        try:
            doi = str(metadata.get("doi") or "").strip().rstrip(".")
            if doi:
                match = self._fetch_crossref_work_by_doi(doi)
                if not match:
                    base["reason"] = "DOI did not resolve in Crossref."
                    return base
                assessed = self._assess_online_metadata_match(metadata, match, "crossref_doi")
                assessed.update({"number": number, "entry": entry, "doi": doi})
                return assessed

            candidates: List[Dict[str, Any]] = []
            candidates.extend(self._search_crossref_works(metadata))
            if allow_serper and not candidates:
                candidates.extend(self._search_serper_works(metadata))
            if not candidates:
                candidates.extend(self._search_openalex_works(metadata))
            if not candidates:
                return base

            scored = [self._assess_online_metadata_match(metadata, candidate, str(candidate.get("source") or "")) for candidate in candidates]
            scored.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
            best = scored[0]
            second_score = float(scored[1].get("score") or 0) if len(scored) > 1 else 0.0
            best_score = float(best.get("score") or 0)
            auto_resolve_enabled = bool((options or {}).get("auto_resolve_unresolved_references", True))
            auto_resolve_min_score = 0.90
            auto_resolve_min_gap = 0.12
            if best_score < 0.72:
                base["reason"] = "Search results did not closely match the supplied reference metadata."
                return base
            score_gap = best_score - second_score
            if second_score >= 0.78 and auto_resolve_enabled and best_score >= auto_resolve_min_score and score_gap >= auto_resolve_min_gap:
                best["status"] = "verified"
                best["reason"] = "Auto-resolved similar online records using confidence gap policy."
                best["auto_resolved"] = True
                best["auto_resolve_chips"] = [
                    "auto_resolve:yes",
                    f"score:{best_score:.2f}",
                    f"second:{second_score:.2f}",
                    f"gap:{score_gap:.2f}",
                    f"threshold_score:{auto_resolve_min_score:.2f}",
                    f"threshold_gap:{auto_resolve_min_gap:.2f}",
                ]
            elif second_score >= 0.78 and abs(score_gap) <= 0.03:
                best["status"] = "ambiguous"
                best["reason"] = "Multiple similar online records matched this reference."
                best["confidence_rejected"] = bool(auto_resolve_enabled)
                best["auto_resolve_chips"] = [
                    "auto_resolve:no",
                    f"score:{best_score:.2f}",
                    f"second:{second_score:.2f}",
                    f"gap:{score_gap:.2f}",
                    f"threshold_score:{auto_resolve_min_score:.2f}",
                    f"threshold_gap:{auto_resolve_min_gap:.2f}",
                ]
            elif best["status"] == "verified" and best_score < 0.93:
                best["status"] = "likely_match"
                best["reason"] = "A strong online match was found, but the citation was matched by search rather than DOI."
            best.update({"number": number, "entry": entry, "doi": str(metadata.get("doi") or "")})
            return best
        except requests.RequestException as exc:
            base["status"] = "error"
            base["reason"] = f"Online lookup failed: {exc.__class__.__name__}."
            return base
        except Exception as exc:
            base["status"] = "error"
            base["reason"] = f"Online validation error: {exc.__class__.__name__}."
            return base

    def _fetch_crossref_work_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """Return Crossref metadata for a DOI when available."""
        normalized_doi = str(doi or "").strip().rstrip(".").lower()
        if not normalized_doi:
            return None
        key = self._cache_key("crossref_doi", {"doi": normalized_doi})
        cached = self._cache_get(key)
        if isinstance(cached, dict):
            return cached

        url = f"https://api.crossref.org/works/{quote(normalized_doi, safe='')}"
        self._increment_online_lookup_metric("crossref_requests")
        response = requests.get(
            url,
            headers={"Accept": "application/json", "User-Agent": "manuscript-editor/1.0"},
            timeout=self.ONLINE_VALIDATION_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        message = payload.get("message") if isinstance(payload, dict) else None
        candidate = self._normalize_crossref_candidate(message) if isinstance(message, dict) else None
        if candidate:
            self._cache_set(key, candidate)
        return candidate

    def _search_crossref_works(self, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search Crossref by bibliographic metadata."""
        title = str(metadata.get("title") or "").strip()
        first_author = self._extract_reference_first_author(str(metadata.get("authors") or ""))
        year = str(metadata.get("year") or "").strip()
        journal = str(metadata.get("journal") or "").strip()
        query = " ".join(part for part in [title, first_author, year, journal] if part).strip()
        if not query:
            return []
        key = self._cache_key("crossref_search", {"query": query, "rows": 5})
        cached = self._cache_get(key)
        if isinstance(cached, list):
            return cached

        self._increment_online_lookup_metric("crossref_requests")
        response = requests.get(
            "https://api.crossref.org/works",
            headers={"Accept": "application/json", "User-Agent": "manuscript-editor/1.0"},
            params={"rows": 5, "query.bibliographic": query},
            timeout=self.ONLINE_VALIDATION_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload.get("message") if isinstance(payload, dict) else {}
        items = message.get("items") if isinstance(message, dict) else []
        normalized: List[Dict[str, Any]] = []
        for item in items if isinstance(items, list) else []:
            candidate = self._normalize_crossref_candidate(item)
            if candidate:
                normalized.append(candidate)
        self._cache_set(key, normalized)
        return normalized

    def _search_openalex_works(self, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback search in OpenAlex when Crossref does not find a title match."""
        title = str(metadata.get("title") or "").strip()
        if not title:
            return []
        key = self._cache_key("openalex_search", {"title": title, "per_page": 5})
        cached = self._cache_get(key)
        if isinstance(cached, list):
            return cached

        self._increment_online_lookup_metric("openalex_requests")
        response = requests.get(
            "https://api.openalex.org/works",
            headers={"Accept": "application/json", "User-Agent": "manuscript-editor/1.0"},
            params={"search": title, "per-page": 5},
            timeout=self.ONLINE_VALIDATION_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") if isinstance(payload, dict) else []
        normalized: List[Dict[str, Any]] = []
        for item in results if isinstance(results, list) else []:
            candidate = self._normalize_openalex_candidate(item)
            if candidate:
                normalized.append(candidate)
        self._cache_set(key, normalized)
        return normalized

    def _normalize_crossref_candidate(self, item: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Convert one Crossref record to internal matching metadata."""
        if not isinstance(item, dict):
            return None
        titles = item.get("title")
        title = titles[0] if isinstance(titles, list) and titles else str(item.get("title") or "")
        container = item.get("container-title")
        journal = container[0] if isinstance(container, list) and container else str(item.get("container-title") or "")
        container_title = str(journal or "").strip()
        issued = item.get("issued", {})
        year = ""
        if isinstance(issued, dict):
            date_parts = issued.get("date-parts")
            if isinstance(date_parts, list) and date_parts and isinstance(date_parts[0], list) and date_parts[0]:
                year = str(date_parts[0][0])
        authors = item.get("author")
        first_author = ""
        authors_list = []
        if isinstance(authors, list):
            if authors and isinstance(authors[0], dict):
                first_author = str(authors[0].get("family") or authors[0].get("name") or "").strip()
            for a in authors:
                if isinstance(a, dict):
                    family = str(a.get("family") or a.get("name") or "").strip()
                    given = str(a.get("given") or "").strip()
                    if family:
                        authors_list.append({"family": family, "given": given})
        editors = item.get("editor")
        editor_name = ""
        if isinstance(editors, list) and editors and isinstance(editors[0], dict):
            editor_name = str(editors[0].get("family") or editors[0].get("name") or "").strip()
        pages = str(item.get("page") or "").strip()
        raw_type = str(item.get("type") or "").strip().lower()
        reference_type = "journal"
        if raw_type in {"proceedings-article", "proceedings", "report-paper"} or re.search(r'(?i)\b(?:proceedings|conference|spie)\b', container_title):
            reference_type = "proceedings"
        elif raw_type in {"book-chapter", "reference-entry"}:
            reference_type = "chapter"
        elif raw_type in {"book", "monograph"}:
            reference_type = "book"
        return {
            "source": "crossref",
            "title": str(title or "").strip(),
            "journal": str(journal or "").strip(),
            "container_title": container_title,
            "year": year,
            "pages": pages,
            "volume": str(item.get("volume") or "").strip(),
            "issue": str(item.get("issue") or "").strip(),
            "place": str(item.get("publisher-location") or "").strip(),
            "publisher": str(item.get("publisher") or "").strip(),
            "editor": editor_name,
            "doi": str(item.get("DOI") or "").strip(),
            "source_url": str(item.get("URL") or "").strip(),
            "first_author": first_author,
            "authors_list": authors_list,
            "reference_type": reference_type,
        }

    def _normalize_openalex_candidate(self, item: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Convert one OpenAlex result to internal matching metadata."""
        if not isinstance(item, dict):
            return None
        location = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
        source = location.get("source") if isinstance(location.get("source"), dict) else {}
        authorships = item.get("authorships")
        first_author = ""
        authors_list = []
        if isinstance(authorships, list):
            for idx, a in enumerate(authorships):
                if isinstance(a, dict):
                    author = a.get("author")
                    if isinstance(author, dict):
                        name = str(author.get("display_name") or "").strip()
                        if name:
                            if idx == 0:
                                first_author = name
                            parts = name.split(' ', 1)
                            if len(parts) == 2:
                                authors_list.append({"family": parts[1], "given": parts[0]})
                            else:
                                authors_list.append({"family": name, "given": ""})
        biblio = item.get("biblio") if isinstance(item.get("biblio"), dict) else {}
        doi = str(item.get("doi") or "").strip()
        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
        return {
            "source": "openalex",
            "title": str(item.get("display_name") or "").strip(),
            "journal": str(source.get("display_name") or "").strip(),
            "year": str(item.get("publication_year") or "").strip(),
            "pages": self._build_pages_value(str(biblio.get("first_page") or ""), str(biblio.get("last_page") or "")),
            "volume": str(biblio.get("volume") or "").strip(),
            "issue": str(biblio.get("issue") or "").strip(),
            "place": "",
            "publisher": "",
            "doi": doi.strip(),
            "source_url": str(item.get("id") or "").strip(),
            "first_author": first_author,
            "authors_list": authors_list,
            "reference_type": "journal",
        }

    def _assess_online_metadata_match(
        self,
        metadata: Dict[str, Any],
        candidate: Dict[str, Any],
        source_label: str,
    ) -> Dict[str, Any]:
        """Score how well one remote metadata record matches the supplied reference."""
        title_score = self._text_similarity(str(metadata.get("title") or ""), str(candidate.get("title") or ""))
        reference_author = self._extract_reference_first_author(str(metadata.get("authors") or ""))
        candidate_author = self._extract_reference_first_author(str(candidate.get("first_author") or ""))
        author_match = bool(reference_author and candidate_author and reference_author == candidate_author)
        year_match = bool(metadata.get("year") and candidate.get("year") and str(metadata.get("year")) == str(candidate.get("year")))
        pages_match = self._page_tokens_match(str(metadata.get("pages") or ""), str(candidate.get("pages") or ""))
        source_type = str(metadata.get("source_type") or "generic")
        ref_publisher = self._normalize_match_text(str(metadata.get("tail") or ""))
        cand_publisher = self._normalize_match_text(str(candidate.get("publisher") or ""))
        publisher_match = bool(ref_publisher and cand_publisher and (cand_publisher in ref_publisher or ref_publisher in cand_publisher))
        score = title_score
        if author_match:
            score += 0.18
        if year_match:
            score += 0.12
        if pages_match:
            score += 0.08
        if publisher_match:
            score += 0.08
        status = "verified"
        reason = "Online metadata matched the supplied reference."
        if title_score < 0.45 or (metadata.get("year") and candidate.get("year") and not year_match and not author_match):
            status = "mismatch"
            reason = "Online metadata conflicts with the supplied reference."
        elif source_type in {"book", "chapter", "website", "generic"} and title_score < 0.60:
            status = "mismatch"
            reason = "Online metadata does not reliably match the non-journal reference."
        elif score < 0.82:
            status = "likely_match"
            reason = "An online record closely matched the supplied reference."
        elif source_label == "crossref_doi" and metadata.get("doi") and candidate.get("doi") and str(metadata.get("doi")).lower() != str(candidate.get("doi")).lower():
            status = "mismatch"
            reason = "The DOI resolved, but the returned metadata did not match the supplied DOI."
        return {
            "status": status,
            "reason": reason,
            "source": source_label,
            "score": round(score, 3),
            "matched_title": str(candidate.get("title") or ""),
            "matched_journal": str(candidate.get("journal") or ""),
            "matched_year": str(candidate.get("year") or ""),
            "matched_pages": str(candidate.get("pages") or ""),
            "matched_volume": str(candidate.get("volume") or ""),
            "matched_issue": str(candidate.get("issue") or ""),
            "matched_place": str(candidate.get("place") or ""),
            "matched_publisher": str(candidate.get("publisher") or ""),
            "matched_container_title": str(candidate.get("container_title") or ""),
            "matched_editor": str(candidate.get("editor") or ""),
            "matched_doi": str(candidate.get("doi") or ""),
            "matched_source_url": str(candidate.get("source_url") or ""),
            "source_url": str(candidate.get("source_url") or ""),
            "matched_first_author": str(candidate.get("first_author") or ""),
            "matched_source_type": str(candidate.get("reference_type") or ""),
            "authors_list": candidate.get("authors_list", []),
        }

    def _extract_reference_first_author(self, author_block: str) -> str:
        """Return a lowercased first-author family name for coarse matching."""
        text = re.sub(r'\bet al\.?$', '', str(author_block or '').strip(), flags=re.IGNORECASE).strip()
        if not text:
            return ""
        primary = re.split(r',|;|\band\b|&', text, maxsplit=1, flags=re.IGNORECASE)[0]
        tokens = re.findall(r"[A-Za-z][A-Za-z'`-]*", primary)
        if not tokens:
            return ""
        return tokens[0].lower()

    def _normalize_match_text(self, value: str) -> str:
        """Lowercase and strip punctuation for reference matching."""
        return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))

    def _text_similarity(self, left: str, right: str) -> float:
        """Return a small heuristic similarity score for metadata matching."""
        left_norm = self._normalize_match_text(left)
        right_norm = self._normalize_match_text(right)
        if not left_norm or not right_norm:
            return 0.0
        if left_norm == right_norm:
            return 1.0
        if left_norm in right_norm or right_norm in left_norm:
            return 0.92
        left_tokens = set(left_norm.split())
        right_tokens = set(right_norm.split())
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = len(left_tokens & right_tokens)
        return (2.0 * overlap) / (len(left_tokens) + len(right_tokens))

    def _page_tokens_match(self, left: str, right: str) -> bool:
        """Compare page/article numbers loosely."""
        left_norm = re.sub(r'[^A-Za-z0-9]+', '', str(left or '').lower())
        right_norm = re.sub(r'[^A-Za-z0-9]+', '', str(right or '').lower())
        if not left_norm or not right_norm:
            return False
        return left_norm == right_norm

    def _build_pages_value(self, first_page: str, last_page: str) -> str:
        """Build a compact pages field from OpenAlex bibliographic fields."""
        first = str(first_page or "").strip()
        last = str(last_page or "").strip()
        if first and last and first != last:
            return f"{first}-{last}"
        return first or last

    def format_references_vancouver_numbered(self, text: str, options: Optional[Dict] = None) -> str:
        """Format manuscript citations/references in Vancouver first-appearance order."""
        profile = self.resolve_journal_profile(options or {})
        renumber_map, ordered_entries = self._build_vancouver_renumber_plan(text)

        lines = text.split('\n')
        output: List[str] = []
        in_references = False
        emitted_references = False

        heading_re = re.compile(r'^\s*references?\s*:?\s*$', flags=re.IGNORECASE)
        section_break_re = re.compile(
            r'^\s*(?:appendix|acknowledg(?:e)?ments?|funding|conflicts?\s+of\s+interest|author\s+contributions?)\s*:?\s*$',
            flags=re.IGNORECASE
        )

        for line in lines:
            if heading_re.match(line):
                in_references = True
                output.append("References")
                if not emitted_references:
                    for new_number, item in enumerate(ordered_entries, start=1):
                        normalized_entry = self._normalize_reference_entry(str(item.get("entry") or ""), profile)
                        output.append(f'[{new_number}] {normalized_entry or str(item.get("entry") or "").strip()}')
                    emitted_references = True
                continue

            if in_references and section_break_re.match(line):
                in_references = False
                output.append(line)
                continue

            if not in_references:
                output.append(self._renumber_citation_blocks(line, renumber_map))
                continue

            continue

        return '\n'.join(output)

    def _number_to_words(self, n: int) -> str:
        """Convert number to words (simplified for 1-100)."""
        ones = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
                'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
                'seventeen', 'eighteen', 'nineteen']
        tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']

        if n < 20:
            return ones[n]
        elif n < 100:
            return tens[n // 10] + ('' if n % 10 == 0 else '-' + ones[n % 10])
        else:
            return 'one hundred'

    def get_corrections(self, original: str, corrected: str) -> List[Dict]:
        """Get list of corrections between original and corrected text."""
        corrections = []

        # Simple word-by-word diff
        orig_words = original.split()
        corr_words = corrected.split()

        for i, (orig, corr) in enumerate(zip(orig_words, corr_words)):
            if orig != corr:
                corrections.append({
                    'position': i,
                    'original': orig,
                    'corrected': corr,
                    'type': 'replacement'
                })

        # Handle length differences
        if len(orig_words) != len(corr_words):
            corrections.append({
                'position': min(len(orig_words), len(corr_words)),
                'original': ' '.join(orig_words[min(len(orig_words), len(corr_words)):]),
                'corrected': ' '.join(corr_words[min(len(orig_words), len(corr_words)):]),
                'type': 'length_change'
            })

        return corrections

    def get_domain_report(self) -> Dict:
        """Return last domain-detection/protection summary."""
        return {
            "profile": self.last_domain_profile,
            "scores": dict(self.last_domain_scores),
            "protected_terms": int(self.last_protected_domain_terms),
            "custom_terms": int(self.last_custom_terms_count),
        }

    def _format_healed_reference(self, best_match: Dict[str, Any], original_metadata: Dict[str, Any], profile: Dict[str, Any]) -> str:
        """Format the matched online metadata into a premium, styled bibliography entry."""
        # 1. Format authors list
        authors_list = best_match.get("authors_list") or []
        formatted_authors = []
        for auth in authors_list:
            family = str(auth.get("family") or "").strip()
            given = str(auth.get("given") or "").strip()
            if not family:
                continue
            given_clean = re.sub(r'[^A-Za-z\s]', '', given)
            given_words = [w for w in given_clean.split() if w]
            initials = []
            for w in given_words:
                if len(w) == 1:
                    initials.append(w.upper())
                elif w.isupper() and len(w) <= 4:
                    initials.extend(list(w))
                elif w:
                    initials.append(w[0].upper())
            
            if bool(profile.get("initials_with_periods")):
                initial_text = "".join(f"{letter}." for letter in initials)
            else:
                initial_text = "".join(initials)
            
            if initial_text:
                formatted_authors.append(f"{family} {initial_text}")
            else:
                formatted_authors.append(family)
        
        if formatted_authors:
            if len(formatted_authors) > 6:
                authors_norm = ", ".join(formatted_authors[:6]) + ", et al"
            else:
                authors_norm = ", ".join(formatted_authors)
        else:
            authors_norm = self._normalize_author_block(str(original_metadata.get("authors") or ""), profile)

        # 2. Format title
        matched_title = best_match.get("matched_title") or best_match.get("title")
        if matched_title:
            title_norm = self._format_reference_title(matched_title, profile)
        else:
            title_norm = self._format_reference_title(str(original_metadata.get("title") or ""), profile)

        # 3. Format journal or book tail details
        ref_type = best_match.get("matched_source_type") or best_match.get("reference_type") or original_metadata.get("source_type") or "journal"
        journal_or_book = ""
        
        if ref_type == "journal" or ref_type == "proceedings":
            matched_journal = best_match.get("matched_journal") or best_match.get("journal")
            if matched_journal:
                journal_norm = self._format_reference_journal(matched_journal, profile)
            else:
                journal_norm = self._format_reference_journal(str(original_metadata.get("journal") or ""), profile)
            
            year = best_match.get("matched_year") or original_metadata.get("year")
            volume = best_match.get("matched_volume") or original_metadata.get("volume")
            issue = best_match.get("matched_issue") or original_metadata.get("issue")
            pages = best_match.get("matched_pages") or original_metadata.get("pages")
            
            tail = ""
            if year:
                tail += str(year).strip()
            if volume:
                tail += f";{str(volume).strip()}"
                if issue:
                    tail += f"({str(issue).strip()})"
            if pages:
                if volume or issue:
                    tail += f":{str(pages).strip()}"
                else:
                    tail += f"; {str(pages).strip()}"
            
            if journal_norm and tail:
                journal_or_book = f"{journal_norm.rstrip('.')}. {tail}"
            elif journal_norm:
                journal_or_book = journal_norm
            else:
                journal_or_book = tail
                
        elif ref_type == "book" or ref_type == "chapter":
            place = best_match.get("matched_place") or original_metadata.get("place")
            publisher = best_match.get("matched_publisher") or original_metadata.get("publisher")
            year = best_match.get("matched_year") or original_metadata.get("year")
            
            tail = ""
            if place and publisher:
                tail += f"{str(place).strip()}: {str(publisher).strip()}"
            elif publisher:
                tail += str(publisher).strip()
            if year:
                if tail:
                    tail += f"; {str(year).strip()}"
                else:
                    tail += str(year).strip()
            
            journal_or_book = tail
        else:
            journal_or_book = str(original_metadata.get("tail") or "")

        pieces = [p.rstrip(".") for p in [authors_norm, title_norm, journal_or_book] if p]
        healed_entry = ". ".join(pieces).strip()
        
        matched_doi = best_match.get("matched_doi") or best_match.get("doi")
        if matched_doi:
            healed_entry += f". doi:{str(matched_doi).strip()}"
            
        healed_entry = re.sub(r'\s+', ' ', healed_entry).strip()
        return healed_entry

    def heal_bibliography(self, text: str, options: Optional[Dict] = None, progress_callback: Optional[Callable] = None) -> str:
        """Autonomous Bibliography Healing: correct authors, verify DOIs, insert publisher, and fix citation order formatting."""
        profile = self.resolve_journal_profile(options or {})
        extracted = self._extract_reference_numbered_entries(text or "")
        healed_entries_by_number: Dict[int, str] = {}
        
        lookup_options = dict(options or {})
        lookup_options["online_reference_validation"] = True
        lookup_options["online_reference_serper_fallback"] = True
        
        total = len(extracted)
        for idx, item in enumerate(extracted):
            number = int(item.get("number") or 0)
            entry = str(item.get("entry") or "").strip()
            if progress_callback:
                progress_callback(20.0 + (float(idx) / max(1, total)) * 60.0, f"Healing reference [{number}] ({idx+1}/{total})...")
            if not entry:
                continue
            
            orig_metadata = self._analyze_reference_entry(entry)
            result = self._validate_reference_online(number, entry, orig_metadata, allow_serper=True, options=lookup_options)
            status = str(result.get("status") or "error")
            
            if status in {"verified", "likely_match"}:
                healed_entry = self._format_healed_reference(result, orig_metadata, profile)
                healed_entries_by_number[number] = healed_entry
            else:
                healed_entry = self._normalize_reference_entry(entry, profile)
                healed_entries_by_number[number] = healed_entry or entry

        if progress_callback:
            progress_callback(85.0, "Resolving citation order & renumbering bibliography...")

        renumber_map, ordered_entries = self._build_vancouver_renumber_plan(text)
        
        lines = text.split('\n')
        output: List[str] = []
        in_references = False
        emitted_references = False
        
        heading_re = re.compile(r'^\s*references?\s*:?\s*$', flags=re.IGNORECASE)
        section_break_re = re.compile(
            r'^\s*(?:appendix|acknowledg(?:e)?ments?|funding|conflicts?\s+of\s+interest|author\s+contributions?)\s*:?\s*$',
            flags=re.IGNORECASE
        )
        
        for line in lines:
            if heading_re.match(line):
                in_references = True
                output.append("References")
                if not emitted_references:
                    for new_number, item in enumerate(ordered_entries, start=1):
                        old_number = int(item.get("number") or 0)
                        healed_entry = healed_entries_by_number.get(old_number)
                        if not healed_entry:
                            healed_entry = self._normalize_reference_entry(str(item.get("entry") or ""), profile) or str(item.get("entry") or "").strip()
                        output.append(f'[{new_number}] {healed_entry}')
                    emitted_references = True
                continue
                
            if in_references and section_break_re.match(line):
                in_references = False
                output.append(line)
                continue
                
            if not in_references:
                output.append(self._renumber_citation_blocks(line, renumber_map))
                continue
                
            continue
            
        return '\n'.join(output)
