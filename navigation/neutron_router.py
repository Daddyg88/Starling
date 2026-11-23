"""Starling's own neutron-star route plotter: the backup for when Spansh is down or can't plot.

It reads a small list of neutron stars (made by tools/build_neutron_list.py, file data/neutron_stars.csv.gz:
name,x,y,z) and finds the route with the fewest jumps, using a neutron supercharge (4x or 6x your range)
wherever one helps. Nothing here needs the internet. If the list file isn't there, it simply does nothing."""
import csv
import gzip
import heapq
import math
import os

from core.paths import DATA_DIR

LIST_FILE = DATA_DIR / "neutron_stars.csv.gz"
MAX_EXPANSIONS = 300000          # give up rather than freeze on a hopeless search


class LocalRouteError(Exception):
    pass


def dist(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def load_list(path=None):
    """[(name, (x, y, z))] from the list file, or [] when there is no usable file."""
    path = path or LIST_FILE
    if not os.path.exists(str(path)):
        return []
    out = []
    try:
        with gzip.open(str(path), "rt", encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                try:
                    out.append((row[0], (float(row[1]), float(row[2]), float(row[3]))))
                except (IndexError, ValueError):
                    continue          # header or damaged row
    except (OSError, EOFError):
        return out
    return out


def jumps_for(distance, jump_range, boosted_range=None):
    """Jumps to cover a distance: the first one may be boosted (from a neutron star)."""
    if boosted_range is None or distance <= jump_range:
        return max(1, math.ceil(distance / jump_range - 1e-9))
    if distance <= boosted_range:
        return 1
    return 1 + math.ceil((distance - boosted_range) / jump_range - 1e-9)


class NeutronRouter:
    def __init__(self, stars=None, path=None):
        self.stars = stars if stars is not None else load_list(path)

    @property
    def ready(self):
        return bool(self.stars)

    def find(self, name):
        key = " ".join(str(name or "").split()).casefold()
        return next((pos for n, pos in self.stars if n.casefold() == key), None)

    def route(self, start_name, start, dest_name, dest, jump_range, supercharge=4):
        """Waypoints in the same shape Spansh gives: [{"system","neutron","jumps","distance_left","x","y","z"}]."""
        if not self.stars:
            raise LocalRouteError("I have no neutron star list.")
        if jump_range <= 0:
            raise LocalRouteError("I don't know your jump range.")
        mult = 6 if int(supercharge) == 6 else 4
        boosted = jump_range * mult
        cell = boosted
        grid = {}
        for i, (_, p) in enumerate(self.stars):
            grid.setdefault((int(p[0] // cell), int(p[1] // cell), int(p[2] // cell)), []).append(i)

        def near(p, radius):
            cx, cy, cz = int(p[0] // cell), int(p[1] // cell), int(p[2] // cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for i in grid.get((cx + dx, cy + dy, cz + dz), ()):
                            d = dist(p, self.stars[i][1])
                            if 0 < d <= radius:
                                yield i, d

        # nodes: -1 start, 0..n-1 stars, -2 goal
        def position(node):
            return start if node == -1 else dest if node == -2 else self.stars[node][1]

        total = dist(start, dest)
        best, came, heap, count = {-1: 0.0}, {}, [(total / boosted, 0.0, -1)], 0
        while heap:
            _, cost, node = heapq.heappop(heap)
            if cost > best.get(node, 1e18):
                continue
            if node == -2:
                break
            count += 1
            if count > MAX_EXPANSIONS:
                raise LocalRouteError("That route was too big for me to work out.")
            here = position(node)
            boost = boosted if node >= 0 else None
            options = []
            for i, d in near(here, boosted if node >= 0 else jump_range * 3):
                options.append((i, jumps_for(d, jump_range, boost) + 0.01))      # the 0.01 prefers fewer stops
            options.append((-2, jumps_for(dist(here, dest), jump_range, boost)))
            for nxt, step in options:
                new = cost + step
                if new < best.get(nxt, 1e18):
                    best[nxt], came[nxt] = new, node
                    heapq.heappush(heap, (new + dist(position(nxt), dest) / boosted, new, nxt))
        if -2 not in came and start_name.casefold() != dest_name.casefold():
            raise LocalRouteError("I couldn't find a way there.")
        chain, node = [], -2
        while node != -1:
            chain.append(node)
            node = came[node]
        chain.reverse()
        out = [self._wp(start_name, start, False, 0, total)]
        previous = -1
        for node in chain:
            p = position(node)
            name = dest_name if node == -2 else self.stars[node][0]
            d = dist(position(previous), p)
            jumps = jumps_for(d, jump_range, boosted if previous >= 0 else None)
            out.append(self._wp(name, p, node >= 0, jumps, dist(p, dest)))
            previous = node
        return out

    @staticmethod
    def _wp(name, p, neutron, jumps, left):
        return {"system": name, "neutron": bool(neutron), "jumps": int(jumps), "distance_left": round(left, 2),
                "x": p[0], "y": p[1], "z": p[2]}
