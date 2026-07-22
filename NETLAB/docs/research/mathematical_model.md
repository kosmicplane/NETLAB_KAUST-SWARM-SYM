# Mathematical model

The time-varying relay graph is `G(t)=(V(t),E(t))`, failed nodes are `F(t)`, active nodes are `V_a(t)=V(t)\\F(t)`, and distance is `d_ij(t)=||p_i(t)-p_j(t)||_2`.

A nominal link gate is one only when the hop is within operational and hard-outage distance, current SNR/SINR meets threshold, current capacity meets threshold, and the metric has not expired. Failure-aware feasibility multiplies this gate by endpoint activity. Chain mode pauses the complete stream on one infeasible active hop. Parallel mode maintains independent branch cursors. Forest mode maintains subtree state. Manual mode preserves operator edges while enforcing the same physical and communication gate.

The analytical link budget is `P_rx=P_tx+G_tx+G_rx-L_total`, thermal noise is `-174+10log10(B)+NF` dBm at the reference temperature, and theoretical capacity is `eta*B*log2(1+SINR)`. Capacity is not labeled achieved throughput.
