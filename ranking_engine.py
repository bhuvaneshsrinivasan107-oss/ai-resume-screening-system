# ============================================================
# AI RESUME RANKING ENGINE
# ============================================================


def normalize_skill(skill):

    return skill.lower().strip()


# ============================================================
# SKILL MATCHING
# ============================================================

def calculate_skill_match(
    candidate_skills,
    required_skills
):

    candidate_skills = [

        normalize_skill(skill)

        for skill in candidate_skills

        if skill
    ]

    required_skills = [

        normalize_skill(skill)

        for skill in required_skills

        if skill
    ]

    matched = []

    missing = []

    for required in required_skills:

        found = False

        for candidate in candidate_skills:

            if (
                required == candidate
                or required in candidate
                or candidate in required
            ):

                found = True

                break

        if found:

            matched.append(
                required
            )

        else:

            missing.append(
                required
            )

    if not required_skills:

        return 0, matched, missing

    score = (

        len(matched)
        /
        len(required_skills)

    ) * 100

    return (
        round(score, 2),
        matched,
        missing
    )


# ============================================================
# STATUS
# ============================================================

def determine_status(score):

    if score >= 75:

        return "Approved"

    elif score >= 45:

        return "Pending"

    return "Rejected"


# ============================================================
# COMPLETE RANKING
# ============================================================

def rank_candidate(
    candidate_skills,
    required_skills
):

    score, matched, missing = calculate_skill_match(
        candidate_skills,
        required_skills
    )

    status = determine_status(
        score
    )

    return {

        "score": score,

        "matched_skills": matched,

        "missing_skills": missing,

        "status": status

    }