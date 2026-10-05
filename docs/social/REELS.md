# Instagram reels: scripts, captions and posting plan

Ten 30-second vertical reels (1080x1920) for the `@arcticpassageatlas` account, one per day (days 1 to 5, then days 6 to 10). They are built by
`video/build_reels.py` from generated narration (voice: Arthur), generated motion clips (labelled "AI-generated
footage" on screen), NASA, USGS and U.S. Coast Guard imagery, and real screenshots of the live site. The built files
are kept on E: (`E:/atlas-reels/out`), not in git.

Accuracy rules for anything posted: no claim that a missing ship is a dark vessel; no claim that a changed pixel is
construction; the route planner is a learning tool, not for navigation.

## Day 1: "The Arctic is opening"
Script: This is the Arctic. It is warming much faster than the rest of the planet. As summer sea ice shrinks, routes that were frozen shut for centuries are starting to open. The Northwest Passage. The Northern Sea Route. On paper, they can cut thousands of kilometres between Asia and Europe. But who is actually watching them? I built a free, open map to find out. Follow for one Arctic story, every day.

Caption: The Arctic is opening up, and almost nobody has a map of it. I built a free, open one. Link in bio. #arctic #northwestpassage #geomatics #gis #remotesensing #climate #maps

## Day 2: "What is geomatics?"
Script: Here is a word you probably do not know: geomatics. It is the science of measuring, mapping, and understanding places, using satellites, GPS, and data. Landsat satellites have photographed Earth since 1972, and the archive has been free to use since 2008. That means anyone can compare the same Arctic shoreline across fifty years. I am studying geomatics at Waterloo, and this is what I do with it. Follow for more.

Caption: Geomatics in 30 seconds. Studying it at @uwaterloo and building with it. #geomatics #gis #landsat #remotesensing #uwaterloo #mapping

## Day 3: "How do you plan a route across the Arctic?"
Script: Ships do not sail in straight lines. They go around land, ice, and shallow water. So how do you plan a route across the Arctic? You turn the ocean into a grid, mark every cell as water or blocked, and let an algorithm search for the shortest clear path. My route planner does exactly that, for the Arctic and the whole world. It is a learning tool, not for navigation. Try it free at arcticpassageatlas.com.

Caption: Route planning is a search problem. Try the planner free (a learning tool, not for navigation): arcticpassageatlas.com #routeplanning #arctic #algorithms #gis #shipping #python

## Day 4: "Seeing sea ice in the dark"
Script: In the Arctic winter, the sun does not rise for weeks. So how do satellites see the ice? Radar. Sentinel-1 sends its own microwave pulses through darkness and clouds, and listens for what bounces back. Calm water and ice scatter radar very differently. Turn that into a map, and you can watch the sea freeze, from space, in the dark. Pretty incredible. More tomorrow.

Caption: Radar sees through the polar night. #sentinel1 #radar #seaice #arctic #remotesensing #copernicus

## Day 5: "A live Arctic map, with an honest warning"
Script: Right now, a weather station in Cambridge Bay, Nunavut, is reporting the temperature. Ships are broadcasting their positions. Satellites pass overhead every day. All of it is public data, and I pulled it into one live map. One honest warning: a missing ship on the map does not mean a missing ship. Coverage in the Arctic is thin. See it live at arcticpassageatlas.com.

Caption: Live Arctic weather and vessel data, with the limits shown next to it: arcticpassageatlas.com #arctic #opendata #maps #gis #geospatial

## Days 6 to 10 (second batch)

Day 6, "Why Cambridge Bay?": a town under two thousand people on the Northwest Passage; Iqaluktuuttiaq, "good fishing place"; Canada's High Arctic Research Station opened there in 2019; the 44 km study area.
Caption: Why a small Arctic town? A small place on a big route is a good place to test a method. #cambridgebay #nunavut #arctic #gis #geomatics

Day 7, "My map flagged 700 changes": the first change-screening run flagged about 700 candidates; many looked like old snow; snow masking, a brightness ceiling and a second pair of years left 42 candidates, which are still only candidates. Narration is sped up about 1.19x to fit 30 seconds.
Caption: Good science means doubting your own map. #remotesensing #landsat #gis #datascience #geomatics

Day 8, "Three ways over the top of the world": Northwest Passage, Northern Sea Route and the Transpolar Route (still mostly theory); each trades distance for ice risk.
Caption: Three Arctic routes, one free planner (a learning tool, not for navigation): arcticpassageatlas.com #arctic #shipping #northwestpassage #northernsearoute #maps

Day 9, "Why only summer images?": optical satellites need sunlight; midsummer has 24-hour sun and deep winter none, so the Landsat analysis uses July and August.
Caption: Geomatics is partly knowing when not to trust the data. #landsat #remotesensing #arctic #midnightsun #geomatics

Day 10, "What a ship dot really means": AIS is a radio message; Arctic receiver coverage is thin; a gap is not suspicious; the shipping heat map drops ship names and ID numbers.
Caption: Honest maps show their blind spots. #ais #maritime #arctic #opendata #gis

## Posting notes
- Post around the same time each day; add arcticpassageatlas.com to the bio link.
- Turn on Instagram's AI label when uploading (the clips marked "AI-generated footage" are generated).
- Footage credits are burned into the frames: NASA, USGS and U.S. Coast Guard imagery is public domain; NASA Blue Marble, MODIS and Landsat views come through NASA GIBS.
- Rebuild after edits: `python video/build_reels.py 3` (one reel) or without arguments (all five).
