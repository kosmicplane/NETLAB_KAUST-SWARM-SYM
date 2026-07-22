from algorithm import step

def test_step_contract():
    snapshot={
        "seed":7,"step_s":0.1,"revision_id":"test","simulation_time_s":1.0,
        "uavs":[
            {"id":"drone_1","active":True,"failed":False,"role":"relay","position":[20,0,30],"velocity":[0,0,0],"battery_soc_pct":100},
            {"id":"drone_2","active":True,"failed":False,"role":"relay","position":[50,0,30],"velocity":[0,0,0],"battery_soc_pct":90},
            {"id":"drone_3","active":True,"failed":False,"role":"standby","position":[80,10,30],"velocity":[0,0,0],"battery_soc_pct":95},
        ],
        "ground_entities":[{"id":"station","type":"ground_station","position":[0,0,1.5]}],
        "topology":{"source":"station","branches":[["drone_1","drone_2"]]},
        "links":[],"flows":[],"packets":{},"constraints":{"minimum_separation_m":4,"service_region":{"center":[100,0,0],"length_m":300,"width_m":150,"min_altitude_m":10,"max_altitude_m":120}},
    }
    result=step(snapshot,{})
    assert isinstance(result,dict)
    assert any(key in result for key in ("desired_positions","traffic_schedule","antenna_commands","metrics","topology_candidate"))
