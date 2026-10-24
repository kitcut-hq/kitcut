D=/srv/kitcut/scratch/h3test
while systemctl is-active -q h3pilot; do sleep 30; done
echo "PILOT_V1_ENDED $(date +%T)"
cd $D && python3 leo_pilot.py plan || { echo "LINT FAILED"; exit 1; }
python3 leo_exp.py plan
cd /srv/kitcut/wan2gp && . .venv/bin/activate
gen() {  # gen <settings.json> <outdir>
  k=$(basename "$1" .json)
  [ -f "$2/$k.mp4" ] && { echo "HAVE $k"; return; }
  echo "BEGIN $k $(date +%s) $(date +%T)"
  python wgp.py --process "$1" --output-dir "$2" --verbose 1
  if [ -f "$2/$k.mp4" ]; then echo "FINISH $k $(date +%s) $(date +%T)"; else echo "FAILED $k $(date +%T) (no output file)"; fi
}
for f in $D/shots/S*.json; do gen "$f" $D/out_v5; done
cd $D && python3 leo_pilot.py assemble out_v5 && echo "V5_DONE $(date +%T)"
cd /srv/kitcut/wan2gp
for f in $D/exp/*.json; do gen "$f" $D/out_exp; done
echo "ALLDONE $(date +%T)"
