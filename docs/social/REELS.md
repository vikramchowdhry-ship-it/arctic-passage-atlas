# Instagram reels: scripts, captions and posting plan

Five 30-second vertical reels (1080x1920) for the `@arcticpassageatlas` account, one per day. They are built by
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

## Posting notes
- Post around the same time each day; add arcticpassageatlas.com to the bio link.
- Turn on Instagram's AI label when uploading (the clips marked "AI-generated footage" are generated).
- Footage credits are burned into the frames: NASA, USGS and U.S. Coast Guard imagery is public domain; NASA Blue Marble, MODIS and Landsat views come through NASA GIBS.
- Rebuild after edits: `python video/build_reels.py 3` (one reel) or without arguments (all five).
