from django.core.exceptions import ValidationError
SKILLS = ('Swift','SwiftUI','UIKit','Combine','CoreData','Core Data','Git','XCTest','URLSession')
def normalized(value):
    return {item.strip().casefold() for item in value.split(',') if item.strip()}
def validate_skills(value):
    if not normalized(value).issubset({item.casefold() for item in SKILLS}):
        raise ValidationError('Допустимые навыки: Swift, SwiftUI, UIKit, Combine, CoreData, Git, XCTest, URLSession.')
    return value
