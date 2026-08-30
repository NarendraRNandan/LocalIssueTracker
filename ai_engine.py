import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.metrics.pairwise import cosine_similarity

# Training dataset of civic complaint descriptions with corresponding categories
TRAINING_DATA = [
    # Roads & Potholes
    ("Huge deep pothole in the middle of the road causing traffic jam and bike accidents", "Roads & Potholes"),
    ("Asphalt is peeling off and deep craters have formed after rain", "Roads & Potholes"),
    ("Broken road surface near signal, dangerous for two wheelers", "Roads & Potholes"),
    ("Tar is completely gone, road full of stones and dust", "Roads & Potholes"),
    ("Speed breaker is not painted and broken into sharp pieces", "Roads & Potholes"),
    ("Road cave in and huge crater near bus stop", "Roads & Potholes"),
    ("Uneven road surface and sunken trench from pipeline digging", "Roads & Potholes"),
    ("Footpath slabs broken and missing, pedestrians forced to walk on busy road", "Roads & Potholes"),
    ("Severe potholes on main road causing long vehicle queues", "Roads & Potholes"),
    ("Unpaved muddy road with deep tire tracks after monsoon", "Roads & Potholes"),

    # Waste & Garbage
    ("Overflowing garbage bin on sidewalk attracting stray dogs and cattle", "Waste & Garbage"),
    ("Huge pile of rotting trash dumped at the street corner", "Waste & Garbage"),
    ("Garbage truck has not collected waste for 5 days, severe stench", "Waste & Garbage"),
    ("Illegal dumping of construction debris and plastic waste in vacant plot", "Waste & Garbage"),
    ("Commercial market waste thrown on roadside blocking pedestrians", "Waste & Garbage"),
    ("Dead animal lying on side of road needs immediate cleanup", "Waste & Garbage"),
    ("Littering and uncleaned dustbins outside school gate", "Waste & Garbage"),
    ("Plastic bags and organic waste decomposing and causing foul smell", "Waste & Garbage"),
    ("Sanitation workers not clearing open dumpster near residential complex", "Waste & Garbage"),

    # Streetlights & Electricity
    ("Streetlight not working for the past two weeks, road is pitch dark at night", "Streetlights & Electricity"),
    ("Flickering street lamp and loose electric cables", "Streetlights & Electricity"),
    ("Live electrical wire hanging dangerously low from pole", "Streetlights & Electricity"),
    ("Electric pole damaged after vehicle collision, bent and at risk of falling", "Streetlights & Electricity"),
    ("Transformer sparking and making loud buzzing noise", "Streetlights & Electricity"),
    ("Entire street has no street lighting, unsafe for women and pedestrians", "Streetlights & Electricity"),
    ("Open junction box with exposed wires on electric pole near playground", "Streetlights & Electricity"),
    ("Streetlights remain switched on during day and off at night due to timer fault", "Streetlights & Electricity"),

    # Water Supply & Drainage
    ("Underground water main pipeline burst and flooding the entire street", "Water Supply & Drainage"),
    ("No municipal drinking water supply in our area for the last 3 days", "Water Supply & Drainage"),
    ("Sewage water overflowing from manhole and spreading on road", "Water Supply & Drainage"),
    ("Stormwater drain clogged with plastic bottles and silt causing waterlogging", "Water Supply & Drainage"),
    ("Contaminated black foul smelling tap water coming in kitchen pipelines", "Water Supply & Drainage"),
    ("Open manhole cover without warning barricade, extreme danger", "Water Supply & Drainage"),
    ("Low water pressure in municipal supply line during morning hours", "Water Supply & Drainage"),
    ("Gutter overflowing after light rain entering ground floor houses", "Water Supply & Drainage"),

    # Public Safety & Traffic
    ("Traffic signal lights not functioning at busy four way crossroads", "Public Safety & Traffic"),
    ("Blind curve with missing convex mirror causing frequent collisions", "Public Safety & Traffic"),
    ("Missing stop sign and speed limit signage near hospital entrance", "Public Safety & Traffic"),
    ("Illegal parking of heavy trucks on both sides of narrow lane", "Public Safety & Traffic"),
    ("Auto rickshaws blocking bus bay and creating dangerous bottleneck", "Public Safety & Traffic"),
    ("Missing guardrail on bridge / flyover ramp", "Public Safety & Traffic"),
    ("Stray dog menace attacking pedestrians and cyclists in early mornings", "Public Safety & Traffic"),

    # Parks & Trees
    ("Huge tree branch fell down and blocked vehicle access", "Parks & Trees"),
    ("Overgrown tree branches touching high voltage power lines", "Parks & Trees"),
    ("Public park children swings and slide broken with sharp edges", "Parks & Trees"),
    ("Overgrown wild bushes in community park providing cover for illegal activities", "Parks & Trees"),
    ("Dying dry tree posing risk of falling on nearby houses during storm", "Parks & Trees"),
    ("Park jogging track broken and grass uncut for months", "Parks & Trees"),

    # Noise & Encroachment
    ("Loudspeakers blaring beyond midnight without police permission", "Noise & Encroachment"),
    ("Illegal street vendors and stalls completely occupying public footpath", "Noise & Encroachment"),
    ("Commercial generator running continuously on residential balcony causing loud noise", "Noise & Encroachment"),
    ("Unauthorized shop extension constructed over drainage channel", "Noise & Encroachment"),
    ("Construction work with heavy machinery operating at 2 AM", "Noise & Encroachment"),

    # Public Infrastructure
    ("Damaged public toilet with broken doors and no water supply", "Public Infrastructure"),
    ("Bus stop shelter roof ripped off by wind, commuters standing in rain", "Public Infrastructure"),
    ("Public park seating bench broken into pieces", "Public Infrastructure"),
    ("Direction signage board rusted and unreadable", "Public Infrastructure"),
    ("Pedestrian subway flooded and lights broken inside", "Public Infrastructure"),
]

# High urgency / hazard risk keywords
URGENT_KEYWORDS = {
    "live wire": 0.95,
    "sparking": 0.90,
    "open manhole": 0.95,
    "flooded": 0.80,
    "burst": 0.85,
    "collapse": 0.90,
    "accident": 0.85,
    "fire": 0.95,
    "hospital": 0.75,
    "danger": 0.70,
    "urgent": 0.80,
    "unsafe": 0.70,
    "sewage overflowing": 0.75,
    "dead animal": 0.70,
    "crater": 0.70,
    "deep pothole": 0.75,
    "contamination": 0.85,
}


class AIEngine:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", max_features=1500)
        self.classifier = MultinomialNB(alpha=0.1)
        self._train_classifier()

    def _train_classifier(self):
        texts = [item[0] for item in TRAINING_DATA]
        labels = [item[1] for item in TRAINING_DATA]
        X = self.vectorizer.fit_transform(texts)
        self.classifier.fit(X, labels)

    def predict_category(self, text):
        """Predicts the civic issue category and confidence score from description."""
        if not text or len(text.strip()) < 3:
            return {"category": "Roads & Potholes", "confidence": 0.5, "all_probabilities": {}}

        clean_text = text.lower().strip()
        X_vec = self.vectorizer.transform([clean_text])
        probs = self.classifier.predict_proba(X_vec)[0]
        classes = self.classifier.classes_

        top_idx = np.argmax(probs)
        top_cat = classes[top_idx]
        confidence = float(probs[top_idx])

        # If confidence is too low, default to heuristic keyword match or top
        prob_dict = {classes[i]: round(float(probs[i]), 3) for i in range(len(classes))}

        return {
            "category": top_cat,
            "confidence": round(confidence, 3),
            "all_probabilities": prob_dict,
        }

    def assess_priority_and_urgency(self, text, category=None):
        """Evaluates issue urgency score (0.0 to 1.0) and assigns priority level."""
        if not text:
            return {"priority": "Medium", "urgency_score": 0.5, "reasons": ["Standard priority"]}

        lower_text = text.lower()
        score = 0.35  # Base score
        matched_reasons = []

        for kw, weight in URGENT_KEYWORDS.items():
            if kw in lower_text:
                score = max(score, weight)
                matched_reasons.append(f"Contains hazard indicator: '{kw}'")

        if category in ["Streetlights & Electricity", "Water Supply & Drainage"]:
            score = max(score, 0.55)

        if score >= 0.85:
            priority = "Urgent"
        elif score >= 0.65:
            priority = "High"
        elif score >= 0.40:
            priority = "Medium"
        else:
            priority = "Low"

        return {
            "priority": priority,
            "urgency_score": round(score, 2),
            "reasons": matched_reasons or ["Standard priority based on description"],
        }

    def find_duplicates(self, new_text, existing_issues, similarity_threshold=0.38):
        """Finds existing similar issues using TF-IDF cosine similarity.
        existing_issues should be a list of Issue models or dicts with id, title, description, case_code, etc.
        """
        if not new_text or not existing_issues:
            return []

        clean_new = new_text.lower().strip()
        corpus = [clean_new]
        issue_map = []

        for issue in existing_issues:
            desc = f"{getattr(issue, 'title', '')} {getattr(issue, 'description', '')}".lower().strip()
            if len(desc) > 3:
                corpus.append(desc)
                issue_map.append(issue)

        if len(corpus) <= 1:
            return []

        try:
            tfidf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
            matrix = tfidf.fit_transform(corpus)
            sims = cosine_similarity(matrix[0:1], matrix[1:])[0]

            duplicates = []
            for idx, sim in enumerate(sims):
                sim_score = float(sim)
                if sim_score >= similarity_threshold:
                    target_issue = issue_map[idx]
                    duplicates.append({
                        "id": target_issue.id,
                        "case_code": getattr(target_issue, "case_code", ""),
                        "title": getattr(target_issue, "title", ""),
                        "category": getattr(target_issue, "category", ""),
                        "status": getattr(target_issue, "status", ""),
                        "locality": getattr(target_issue, "locality_address", "") or getattr(target_issue, "city_town", ""),
                        "upvotes": getattr(target_issue, "upvote_count", 0),
                        "similarity_score": round(sim_score * 100, 1),
                    })

            # Sort by similarity descending
            duplicates.sort(key=lambda x: x["similarity_score"], reverse=True)
            return duplicates[:4]
        except Exception:
            return []

    def generate_action_summary(self, title, description, category):
        """Generates a concise action triage summary for municipal authorities."""
        t = (title or "").strip()
        d = (description or "").strip()
        combined = f"{t}. {d}"
        if len(combined) > 140:
            combined = combined[:137] + "..."
        return combined


# Global singleton instance
ai_engine = AIEngine()
