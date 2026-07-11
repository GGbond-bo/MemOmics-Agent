#!/usr/bin/env python3
"""Build hybrid search index for MemOmics skill matching.
Combines: keyword aliases + TF-IDF char ngram + domain boost.
"""
import json, os, sys, time, pickle, re
from collections import defaultdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Project root is 3 levels up from this file: tools/ -> hermes-agent/ -> project root
_script_dir = os.path.abspath(__file__)
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_script_dir)))
SKILLS_DIR = os.path.join(_PROJ_ROOT, 'hermes_home', 'skills', 'bioinformatics')
INDEX_FILE = os.path.join(os.path.dirname(_script_dir), 'skill_hybrid_index.pkl')

def read_skill_desc(skill_dir):
    """Read SKILL.md frontmatter and extract name, description, keywords."""
    md = os.path.join(SKILLS_DIR, skill_dir, 'SKILL.md')
    if not os.path.exists(md):
        return None
    with open(md, encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    info = {'name': skill_dir, 'description': '', 'when_to_use': '', 'tags': [], 'keywords': []}
    
    # Parse YAML frontmatter
    lines = content.split('\n')
    if not lines or lines[0].strip() != '---':
        return info
    
    yaml_lines = []
    in_yaml = False
    for i, line in enumerate(lines):
        if i == 0:
            in_yaml = True
            continue
        if in_yaml and line.strip() == '---':
            break
        if in_yaml:
            yaml_lines.append(line)
    
    yaml_text = '\n'.join(yaml_lines)
    try:
        import yaml
        data = yaml.safe_load(yaml_text) or {}
    except:
        # Simple line-based parsing as fallback
        data = {}
        for line in yaml_lines:
            if ':' in line:
                k, v = line.split(':', 1)
                data[k.strip()] = v.strip().strip("'").strip('"')
    
    info['description'] = str(data.get('description', '') or '').strip()
    info['when_to_use'] = str(data.get('when_to_use', '') or '').strip()
    info['name'] = str(data.get('name', skill_dir)).strip()
    
    # Extract tags
    tags = data.get('tags', [])
    if isinstance(tags, list):
        info['tags'] = [str(t).strip() for t in tags if t]
    elif isinstance(tags, str):
        info['tags'] = [t.strip() for t in tags.split(',') if t.strip()]
    
    # Build keyword list: skill name tokens + description keywords + tags
    keywords = set()
    # Add skill directory name tokens
    for token in re.split(r'[-_\s]', skill_dir):
        token = token.strip().lower()
        if len(token) >= 2:
            keywords.add(token)
    # Add description + when_to_use words
    desc_lower = (info['description'] + ' ' + info['when_to_use']).lower()
    for word in re.findall(r'[a-z\u4e00-\u9fff]{2,}', desc_lower):
        keywords.add(word)
    # Add tags
    for tag in info['tags']:
        for token in re.split(r'[-_\s]', tag):
            token = token.strip().lower()
            if len(token) >= 2:
                keywords.add(token)
    
    info['keywords'] = sorted(keywords)
    return info


def build_index():
    """Build and save hybrid search index."""
    print("Building hybrid search index...")
    
    if not os.path.exists(SKILLS_DIR):
        print(f"ERROR: skills dir not found: {SKILLS_DIR}")
        return False
    
    all_skills = {}
    skill_dirs = sorted([d for d in os.listdir(SKILLS_DIR) 
                        if os.path.isdir(os.path.join(SKILLS_DIR, d)) 
                        and not d.startswith('.')])
    
    for sd in skill_dirs:
        info = read_skill_desc(sd)
        if info:
            all_skills[sd] = info
    
    print(f"  Loaded {len(all_skills)} skill descriptions")
    
    # Build search corpus: name + description + keywords
    corpus = []
    corpus_skills = []
    for name, info in all_skills.items():
        text = f"{info['name']} {info['description']} {info['when_to_use']} {' '.join(info['keywords'])}"
        corpus.append(text)
        corpus_skills.append(name)
    
    # TF-IDF with character n-grams (supports Chinese + English)
    vectorizer = TfidfVectorizer(
        analyzer='char_wb',     # word-boundary character ngrams
        ngram_range=(2, 4),     # 2-4 char ngrams
        max_features=5000,
        sublinear_tf=True,      # 1 + log(tf)
        strip_accents='unicode',
        lowercase=True,
    )
    
    tfidf_matrix = vectorizer.fit_transform(corpus)
    print(f"  TF-IDF matrix: {tfidf_matrix.shape}")
    print(f"  Vocabulary size: {len(vectorizer.vocabulary_)}")
    
    # Build keyword alias index
    keyword_index = defaultdict(list)
    for name, info in all_skills.items():
        # Add skill name itself
        keyword_index[name.lower()].append((name, 0.9))
        # Add each keyword
        for kw in info['keywords']:
            if len(kw) >= 2:
                keyword_index[kw.lower()].append((name, 0.7))
        # Add name tokens
        for token in re.split(r'[-_\s]', name):
            token = token.strip().lower()
            if len(token) >= 2:
                keyword_index[token].append((name, 0.6))
    
    # Build domain index
    domain_file = os.path.join(os.path.dirname(_script_dir), 'skill_domain_index.json')
    skill_domains = {}
    if os.path.exists(domain_file):
        with open(domain_file, encoding='utf-8') as f:
            dom_idx = json.load(f)
        for domain, skills in dom_idx.get('domains', {}).items():
            for s in skills:
                skill_domains[s] = domain
    
    # Save index
    index_data = {
        'vectorizer': vectorizer,
        'tfidf_matrix': tfidf_matrix,
        'corpus_skills': corpus_skills,
        'keyword_index': dict(keyword_index),
        'skill_domains': skill_domains,
        'skill_info': all_skills,
        'built_at': time.time(),
    }
    
    with open(INDEX_FILE, 'wb') as f:
        pickle.dump(index_data, f)
    
    print(f"  Index saved to {INDEX_FILE}")
    print(f"  {len(corpus_skills)} skills, {len(keyword_index)} keyword entries")
    return True


if __name__ == '__main__':
    os.chdir(_PROJ_ROOT)
    build_index()
