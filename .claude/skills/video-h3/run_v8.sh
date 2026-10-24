D=/srv/kitcut/scratch/h3test
mkdir -p $D/shots_v7 && cp -f $D/out_v7/*.json $D/shots_v7/ 2>/dev/null
cd $D && python3 leo_pilot.py plan || { echo "LINT FAILED"; exit 1; }
mkdir -p $D/out_v8 && cp -f $D/shots/*.json $D/out_v8/
# a shot whose settings and reference pictures are identical to v7's is the same render: reuse it
for f in $D/shots/S*.json; do
  k=$(basename "$f" .json)
  python3 -c "import json,sys; a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2])); sys.exit(0 if all(a.get(x)==b.get(x) for x in ('prompt','image_refs','model_type','config','seed','video_length')) else 1)" "$f" "$D/shots_v7/$k.json" 2>/dev/null && [ "$k" != S01 ] && [ "$k" != S03 ] && [ "$k" != S06 ] && [ "$k" != S07 ] && [ "$k" != S08 ] && [ "$k" != S10 ] && [ "$k" != S11 ] && cp $D/out_v7/$k.mp4 $D/out_v8/$k.mp4 && echo "REUSED $k from v7"
done
cd /srv/kitcut/wan2gp && . .venv/bin/activate
gen() {  # gen <settings.json> <outdir>
  k=$(basename "$1" .json)
  [ -f "$2/$k.mp4" ] && { echo "HAVE $k"; return; }
  echo "BEGIN $k $(date +%s) $(date +%T)"
  python wgp.py --process "$1" --output-dir "$2" --verbose 1
  if [ -f "$2/$k.mp4" ]; then echo "FINISH $k $(date +%s) $(date +%T)"; else echo "FAILED $k $(date +%T) (no output file)"; fi
}
for f in $D/shots/S*.json; do gen "$f" $D/out_v8; done
cd $D && python3 leo_pilot.py assemble out_v8 && echo "V8_DONE $(date +%T)"
# yield: the same v8 shot with two more seeds (with the cabin reference, the setup we would use)
cd $D && rm -rf exp && python3 leo_exp.py plan && rm -f exp/S06_pdd.json exp/S06_5s.json
cd /srv/kitcut/wan2gp
for f in $D/exp/*.json; do gen "$f" $D/out_exp8; done
echo "ALLDONE $(date +%T)"
