from ai_engine.scoring.rules.objective_scoring import OBJECTIVE_RULES
from ai_engine.scoring.rules.phase1_before_arrival import PHASE1_RULES
from ai_engine.scoring.rules.phase2_arrival_step1 import PHASE2_RULES
from ai_engine.scoring.rules.phase3_arrival_step2 import PHASE3_RULES
from ai_engine.scoring.rules.phase4_arrival_step3 import PHASE4_RULES
from ai_engine.scoring.rules.phase5_arrival_step4 import PHASE5_RULES
from ai_engine.scoring.rules.phase6_arrival_step5 import PHASE6_RULES

ALL_RULES = (
    PHASE1_RULES
    + PHASE2_RULES
    + PHASE3_RULES
    + PHASE4_RULES
    + PHASE5_RULES
    + PHASE6_RULES
    + OBJECTIVE_RULES
)
