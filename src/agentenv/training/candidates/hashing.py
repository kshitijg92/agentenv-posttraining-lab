from agentenv.hashing import hash_json
from agentenv.training.candidates.schema import TrainingCandidateRecord


def hash_training_candidate_record(record: TrainingCandidateRecord) -> str:
    return hash_json(record.model_dump(mode="json"))
