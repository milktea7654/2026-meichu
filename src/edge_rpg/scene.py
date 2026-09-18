"""Validate the board perception boundary before any world mutation."""
import math


def number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def probability(value):
    return number(value) and 0 <= value <= 1


def label(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 128


def validate_observation(observation, now, max_age):
    if not isinstance(observation, dict):
        raise ValueError('SceneObservation must be an object')
    timestamp = observation.get('timestamp')
    scene = observation.get('scene')
    confidence = observation.get('scene_confidence')
    indoor = observation.get('indoor_probability')
    objects = observation.get('objects')
    if not number(timestamp) or not 0 <= now-timestamp <= max_age:
        raise ValueError('SceneObservation timestamp must be fresh and finite')
    if not label(scene) or not probability(confidence) or not probability(indoor):
        raise ValueError('SceneObservation labels or probabilities are invalid')
    if not isinstance(objects, list) or len(objects) > 256:
        raise ValueError('SceneObservation objects must be a bounded list')
    validated = []
    for obj in objects:
        if not isinstance(obj, dict) or not label(obj.get('class')) or not probability(obj.get('confidence')):
            raise ValueError('SceneObservation object is invalid')
        validated.append({'class': obj['class'], 'confidence': obj['confidence']})
    # Keep only the supported data contract, with no mutable backend-owned objects.
    return {'timestamp': timestamp, 'scene': scene, 'scene_confidence': confidence,
            'indoor_probability': indoor, 'objects': validated}
