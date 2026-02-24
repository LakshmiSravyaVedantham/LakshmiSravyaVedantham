# Exquisite Corpse — Week 1
# Revealed: 2026-02-24
# Contributors (1): @LakshmiSravyaVedantham
#------------------------------------------------------------
    return sorted(data, key=lambda x: x['entropy'], reverse=True)

# --- @LakshmiSravyaVedantham ---
    entropy_map = {k: -sum(p * math.log2(p) for p in v if p > 0) for k, v in distributions.items()}
    ranked = sorted(entropy_map.items(), key=lambda item: item[1], reverse=True)
    top_keys = [k for k, _ in ranked[:threshold]]
