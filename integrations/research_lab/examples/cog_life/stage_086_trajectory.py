"""COG086 phase-balanced distinct acquisition trajectories, pre-outcome amendment."""
from random import Random
from stage_084_086_data import CUES,number,practice_frame

def practice_trajectory(seed,n,held):
    if type(n) is not int or n<16 or n%8 or type(held) is not int or held<8 or held%8:
        raise ValueError("balanced synthetic episode bounds required")
    data=[];queries=[];sealed=[]
    for skill in ("early","later"):
        order=list(range(n))
        Random(number(seed,"replay-acquisition-order-v2",skill)).shuffle(order)
        for j in order:
            i=j%8
            cues=(CUES[i],"shared" if j%4!=0 else skill)
            feedback=int(i<4 if skill=="early" else i>=4)
            case=number(seed,"practice-v2",skill,j)
            data.append(dict(phase=skill,episode=case,visible=practice_frame(case,len(data),cues,feedback)))
        for j in range(held):
            i=j%8; ctx=number(seed,"delayed-v2",skill,j)
            queries.append(dict(query=ctx,phase=skill,cues=[CUES[i],skill]))
            sealed.append(dict(query=ctx,feedback=int(i<4 if skill=="early" else i>=4)))
    return data,queries,sealed
