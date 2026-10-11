from django.db import migrations


def canonicalize(apps, schema_editor):
    labels=('Swift','SwiftUI','UIKit','Combine','CoreData','Git','XCTest','URLSession')
    aliases={x.casefold():x for x in labels}
    aliases['core data']='CoreData'
    for app_name,model_name in [('profiles','Profile'),('hiring','Need')]:
        model=apps.get_model(app_name,model_name)
        for obj in model.objects.using(schema_editor.connection.alias).iterator():
            values=[];seen=set()
            for item in obj.skills.split(','):
                item=item.strip()
                if not item:continue
                canonical=aliases.get(item.casefold(),item)
                if canonical.casefold() not in seen:
                    seen.add(canonical.casefold());values.append(canonical)
            text=', '.join(values)
            if obj.skills!=text:
                model.objects.using(schema_editor.connection.alias).filter(pk=obj.pk).update(skills=text)


class Migration(migrations.Migration):
    dependencies=[('profiles','0001_initial'),('hiring','0001_initial')]
    operations=[migrations.RunPython(canonicalize,migrations.RunPython.noop)]
