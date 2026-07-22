# Runtime status and safety-shield decision for one algorithm.
std_msgs/Header header
string algorithm_id
string algorithm_version
string state
string run_id
string revision_id
bool worker_healthy
bool action_accepted
bool fallback_active
float64 last_execution_ms
uint64 deadline_misses
uint64 rejection_count
string details_json
