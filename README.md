# GripApertureRedux

A python-based motion-capture (Optitrack) paradigm, comparing grip-aperture (of the thumb/finger) scaling when reaching pincer-grip a target object in the presence of a distractor object. Critically, this paradigm consists of two phases:

1. When the reaching motion is initiated prior to target reveal (aka a go-before-you-know phase).
2. When the reaching motion is initiated with full knowledge of the target.

In pt. 1, target reveal (an illumination of its placeholder) is triggered when the reaching motion exceeds a velocity threshold.

Running this paradigm requires that you have:
- An Optitrack motion-capture system
- A pair of occlusion goggles (i.e., PLATO)
- An arduino board (for controlling goggles)
- KLibs (a python-based experiment development framework)

As it stands, an Optitrack system is a hard requirement. In theory both the brand of goggles or arduino board shouldn't matter too much, though the code would need to be adapted accordingly. KLibs is also necessary. 

##### Todo:
- [ ] Test script
- [ ] Implement some sort of movement insurance, either:
    - [ ] Min velocity
    - [ ] Tighter MT cutoffs
- [ ] Depending on the above, pull sensible defaults from extant lit
- [ ] Implement movement end-zones
    - [ ] Use these to mark movement end
