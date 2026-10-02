def calibration_bins(rows,bins=10):
    out=[]
    for i in range(bins):
        lo=i/bins;hi=(i+1)/bins;g=[r for r in rows if lo<=float(r.get("predicted_success",0))<hi+(1e-9 if i==bins-1 else 0)]
        if g:out.append({"range":[lo,hi],"n":len(g),"predicted":sum(float(r["predicted_success"]) for r in g)/len(g),"observed":sum(bool(r.get("success")) for r in g)/len(g)})
    return out
