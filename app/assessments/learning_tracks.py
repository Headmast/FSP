"""Explicit catalog; legacy iOS content and versions stay intact."""
from . import learning_content as ios
from . import learning_android as android
from . import learning_flutter as flutter
from . import learning_aurora as aurora

TRACKS = {
    'ios': {'name': 'iOS', 'stack': 'Swift / SwiftUI', 'material': ios, 'exam': True},
    'android': {'name': 'Android', 'stack': 'Kotlin / Jetpack Compose', 'material': android, 'exam': False},
    'flutter': {'name': 'Flutter', 'stack': 'Dart / Widgets', 'material': flutter, 'exam': False},
    'aurora': {'name': 'Аврора', 'stack': 'C++ / Qt / QML', 'material': aurora, 'exam': False},
}


def get_track(slug):
    if slug not in TRACKS:
        raise ValueError('Выберите существующий трек разработки.')
    return TRACKS[slug]


def track_context(slug):
    track = get_track(slug)
    return {'track': slug, 'track_name': track['name'], 'track_stack': track['stack'], 'exam_enabled': track['exam']}
