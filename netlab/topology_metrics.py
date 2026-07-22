from __future__ import annotations
import collections,math
from typing import Hashable,Iterable
Node=Hashable

def adjacency(nodes:Iterable[Node],edges:Iterable[tuple[Node,Node]],directed=False):
 a={n:set() for n in nodes}
 for u,v in edges:a.setdefault(u,set()).add(v);a.setdefault(v,set());
 for u,v in edges:
  if not directed:a[v].add(u)
 return a
def components(a):
 seen=set();out=[]
 for n in a:
  if n in seen:continue
  q=[n];seen.add(n);c=[]
  while q:
   u=q.pop();c.append(u)
   for v in a[u]:
    if v not in seen:seen.add(v);q.append(v)
  out.append(c)
 return out
def shortest_paths(a,src):
 d={src:0};q=collections.deque([src])
 while q:
  u=q.popleft()
  for v in a[u]:
   if v not in d:d[v]=d[u]+1;q.append(v)
 return d
def articulation_points(nodes,edges):
 a=adjacency(nodes,edges);time=0;disc={};low={};parent={};points=set()
 def dfs(u):
  nonlocal time;time+=1;disc[u]=low[u]=time;children=0
  for v in a[u]:
   if v not in disc:
    parent[v]=u;children+=1;dfs(v);low[u]=min(low[u],low[v])
    if u not in parent and children>1:points.add(u)
    if u in parent and low[v]>=disc[u]:points.add(u)
   elif parent.get(u)!=v:low[u]=min(low[u],disc[v])
 for n in a:
  if n not in disc:dfs(n)
 return sorted(points,key=str)
def bridges(nodes,edges):
 a=adjacency(nodes,edges);disc={};low={};parent={};time=0;out=[]
 def dfs(u):
  nonlocal time;time+=1;disc[u]=low[u]=time
  for v in a[u]:
   if v not in disc:
    parent[v]=u;dfs(v);low[u]=min(low[u],low[v]);
    if low[v]>disc[u]:out.append((u,v))
   elif parent.get(u)!=v:low[u]=min(low[u],disc[v])
 for n in a:
  if n not in disc:dfs(n)
 return out
def graph_metrics(nodes,edges):
 nodes=list(nodes);edges=list(edges);a=adjacency(nodes,edges);comps=components(a);dist=[]
 for n in nodes:dist.extend(shortest_paths(a,n).values())
 diameter=max(dist,default=0);degrees=[len(a[n]) for n in nodes]
 return {'node_count':len(nodes),'edge_count':len(edges),'connected_components':len(comps),'diameter_hops':diameter,'average_degree':sum(degrees)/len(degrees) if degrees else 0,'edge_density':2*len(edges)/(len(nodes)*(len(nodes)-1)) if len(nodes)>1 else 0,'articulation_points':articulation_points(nodes,edges),'bridges':bridges(nodes,edges),'redundancy_level':max(0,len(edges)-len(nodes)+len(comps))}
