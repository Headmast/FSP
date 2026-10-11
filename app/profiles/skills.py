from django.core.exceptions import ValidationError
SKILLS = ('Swift','SwiftUI','UIKit','Combine','CoreData','Git','XCTest','URLSession')
SKILL_LABELS = {item.casefold():item for item in SKILLS}
ALIASES = {**{item.casefold():item.casefold() for item in SKILLS}, 'core data':'coredata'}

def canonical_skill(value):
    token=value.strip().casefold()
    return SKILL_LABELS.get(ALIASES.get(token,token),value.strip())

def normalized(value):
    return {ALIASES.get(item.strip().casefold(),item.strip().casefold())
            for item in value.split(',') if item.strip()}
def validate_skills(value):
    tokens=normalized(value)
    if not tokens.issubset(SKILL_LABELS):
        raise ValidationError('Допустимые навыки: Swift, SwiftUI, UIKit, Combine, CoreData, Git, XCTest, URLSession.')
    return ', '.join(item for item in SKILLS if item.casefold() in tokens)
