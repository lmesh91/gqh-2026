"""Exact value and certified upper bound for the probability that a backbone hop is abandoned.

A hop is launched at most four times.  Launch k is unconfirmed if the data or its hop receipt is lost:
    u_k = 1 - exp(-0.02 d_k) exp(-0.02 r_k),
with d_k the moving-receiver path length of launch k and r_k that of the receipt sent back on arrival.  Losses are
independent, so P(abandon) = u_1 u_2 u_3 u_4.

* exact: the retry launches at the times the hop timer sets, t_{k+1} = t_k + 2 (flight_k) + 1 h, and each u_k uses
  its own geometry.  This is the probability when the queue is empty and the link stays open, which holds in every
  S1 run (queues of a few packets, so waits of seconds).
* bound: each retry may also be delayed by up to D hours (queue or anything else), so launch k lies in
  [t_k, t_k + (k - 1) D].  No node moves faster than Mercury at perihelion (0.00142 AU/h), and the receiver's
  arrival time moves with the emission time to within 1e-3, so a path length changes by at most
  L_D = 2 x 0.00142 x 1.001 < 0.0029 AU per hour of emission time.  Then d <= d_k + L_D (k - 1) D for the data and the
  same for the receipt, and since u is increasing in both lengths, the product of these worst cases bounds
  P(abandon) for every retry timing within the window.
* frozen: the earlier approximation, u_1^4 (geometry of the first launch for all four).
The link must also stay open across each window, otherwise the retry waits longer than D.  We certify this with the
clearance's own Lipschitz bound (0.00146 AU/h, e4_scan.py): the window is certified open if the clearance at its start
exceeds 0.10 AU + 0.00146 x window length.
"""
import math
from geom import flight, EXCLUSION_AU

HOUR = 3600.0
L_D = 0.0029            # AU per hour, bound on |d(path length)/d(emission time)|
L_CLR = 0.00146         # AU per hour, bound on |d(clearance)/d(emission time)|


def u(d, r):
    return 1 - math.exp(-0.02 * d) * math.exp(-0.02 * r)


def hop_abandon(a, b, te, delay_h=24.0):
    t = te
    exact, bound, launches, certified = 1.0, 1.0, [], True
    for k in range(4):
        ta, d, c = flight(a, b, t)
        _, r, cr = flight(b, a, ta)
        grow = L_D * k * delay_h
        uk, ub = u(d, r), u(d + grow, r + grow)
        exact *= uk
        bound *= ub
        win = k * delay_h + 2 * (ta - t) / HOUR + 1
        certified &= c - L_CLR * win >= EXCLUSION_AU and cr - L_CLR * win >= EXCLUSION_AU
        launches.append(dict(t_h=t / HOUR, d=d, r=r, u=uk, u_bound=ub))
        t = t + 2 * (ta - t) + HOUR
    first = launches[0]['u']
    return dict(exact=exact, bound=bound, frozen=first ** 4, open_certified=certified, delay_h=delay_h,
                launches=launches)
