"""Backtest CORREGIDO — ordenes estrictamente PASIVAS (maker), sin cruzar el spread.

Correccion vs v1: antes el bid@0.90 CRUZABA y compraba el favorito al ask (~0.55)
en toda ventana = apuesta direccional, NO el arb pasivo. Ahora:
  leg1 (favorito@X): solo llena PASIVO -> una SELL del favorito a precio<=X
       cuando el ask del favorito > X (el bid descansa de verdad). fee maker 0.
  leg2 (longshot@Y): idem, SELL del longshot a <=Y con ask>Y.
Sin marketable/cross. Asi solo opera cuando el mercado realmente esta en el extremo.
"""
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
X, Y, SIZE, TIMEOUT, MIN_CLOSE, MAX_CYCLES = 0.90, 0.07, 10, 30, 60, 5

uni = pd.read_parquet(ROOT/"data/interim/backtest_universe.parquet")
tk = pd.read_parquet(ROOT/"data/interim/trades_bt.parquet"); tk["ts"]=tk.ts_ms/1000.0
ob = pd.read_parquet(ROOT/"data/interim/ob_bt.parquet")
tk_by={m:g for m,g in tk.groupby("market_id")}; ob_by={m:g for m,g in ob.groupby("market_id")}

WIN=[]
for r in uni.itertuples(index=False):
    m=r.market_id
    if m not in tk_by or m not in ob_by: continue
    t0,t1=r.ts_open,r.ts_close
    g=tk_by[m]; gw=g[(g.ts>=t0)&(g.ts<t1)]; ogm=ob_by[m]
    toks={}
    for oc in ("Up","Down"):
        gt=gw[gw.outcome==oc].sort_values("ts")
        ot=ogm[(ogm.outcome==oc)&(ogm.sec>=t0-3600)&(ogm.sec<t1)].sort_values("sec")
        px=gt.price.values.astype(float)
        sz_usdc=gt.size_usdc.values.astype(float)
        toks[oc]=dict(ts=gt.ts.values.astype(float),px=px,
            # ticks.size_usdc is notional; passive BUY fill capacity is shares.
            sh=np.divide(sz_usdc, px, out=np.zeros_like(sz_usdc), where=px>0),
            sell=(gt.side.values=="SELL"),
            osec=ot.sec.values.astype(float),oask=ot.best_ask.values.astype(float),
            obid=ot.best_bid.values.astype(float),obsz=ot.best_bid_size.values.astype(float))
    def bid0(oc):
        a=toks[oc]; i=np.searchsorted(a["osec"],t0,"right")-1
        return a["obid"][i] if i>=0 and len(a["obid"]) else 0.0
    fav="Up" if bid0("Up")>=bid0("Down") else "Down"; lon="Down" if fav=="Up" else "Up"
    WIN.append(dict(t0=t0,t1=t1,fav=fav,lon=lon,fav_won=(r.outcome==fav),tok=toks))
print(f"{len(WIN)} ventanas\n")

def ask_at(a,t):
    s=a["osec"]; i=np.searchsorted(s,t,"right")-1
    return a["oask"][i] if i>=0 else None

def fill_passive(a,t_post,deadline,P,mode):
    """fill PASIVO full-size: SELL a <=P cuando ask>P y cubre cola + SIZE shares."""
    ts=a["ts"]; lo=np.searchsorted(ts,t_post,"right"); hi=np.searchsorted(ts,deadline,"right")
    # queue inicial (pesimista): best_bid_size esta en shares del libro CLOB.
    i0=np.searchsorted(a["osec"],t_post,"right")-1
    queue=0.0 if mode=="opt" else (a["obsz"][i0] if i0>=0 and abs(a["obid"][i0]-P)<0.01 else 0.0)
    need=queue+SIZE
    cum=0.0
    for k in range(lo,hi):
        if a["sell"][k] and a["px"][k]<=P:
            ak=ask_at(a,a["ts"][k])
            if ak is not None and ak>P:      # pasivo de verdad (no cruzamos)
                cum+=a["sh"][k]
                if cum>=need: return (a["ts"][k],P)
    return None

TAKER_FEE=0.018
def run(mode, hedge):
    pnls=[]; n_ok=0; n_leg=0; n_hedge=0; n_traded=0; hedge_asks=[]
    for w in WIN:
        fa=w["tok"][w["fav"]]; lo=w["tok"][w["lon"]]; t0,t1=w["t0"],w["t1"]
        pnl=0.0; t=t0; cyc=0; traded=False
        while t<t1-MIN_CLOSE and cyc<MAX_CYCLES:
            f1=fill_passive(fa,t,t1,X,mode)
            if f1 is None: break
            traded=True; t1ts=f1[0]; c1=X
            f2=fill_passive(lo,t1ts,min(t1ts+TIMEOUT,t1),Y,mode)
            if f2 is not None:
                pnl+=(1.0-X-Y)*SIZE; n_ok+=1; t=f2[0]
            elif hedge:
                # hedge de emergencia: comprar longshot a mercado (taker) al timeout
                th=min(t1ts+TIMEOUT,t1); ak=ask_at(lo,th)
                if ak is not None and ak>0:
                    pnl+=(1.0-X-ak*(1+TAKER_FEE))*SIZE; n_hedge+=1
                    hedge_asks.append(ak)
                else:  # sin ask -> aguantar
                    pnl+=((1.0 if w["fav_won"] else 0.0)-c1)*SIZE; n_leg+=1
                t=th
            else:
                pnl+=((1.0 if w["fav_won"] else 0.0)-c1)*SIZE; n_leg+=1; t=t1ts+TIMEOUT
            cyc+=1
        if traded: n_traded+=1
        pnls.append(pnl)
    pnls=np.array(pnls); tot=n_ok+n_leg+n_hedge
    tag="HEDGE" if hedge else "HOLD"
    print(f"=== {'OPT' if mode=='opt' else 'PES'} / riesgo={tag} ===")
    print(f"  operaron {n_traded}/{len(WIN)} | completos {n_ok} hedged {n_hedge} legged {n_leg}")
    print(f"  PnL total {pnls.sum():+.1f} | /win media {pnls.mean():+.3f} mediana {np.median(pnls):+.3f} | %win+ {(pnls>0).mean()*100:.0f}\n")
    if hedge_asks:
        ha=np.array(hedge_asks)
        print(f"  hedge ask mean {ha.mean():.3f} median {np.median(ha):.3f} "
              f"pct<=0.12 {(ha<=0.12).mean()*100:.1f}%\n")

for hedge in (False, True):
    run("opt", hedge); run("pes", hedge)
