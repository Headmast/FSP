from typing import Annotated,Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator


class Changes(BaseModel):
    model_config=ConfigDict(extra='forbid')
    @model_validator(mode='after')
    def nonempty(self):
        if not self.model_dump(exclude_none=True):raise ValueError('Нужно хотя бы одно изменение.')
        return self


class ProfileChanges(Changes):
    name:Annotated[str,Field(max_length=80)]|None=None
    city:Annotated[str,Field(max_length=80)]|None=None
    skills:Annotated[str,Field(max_length=200)]|None=None
    specialization:Literal['ios_swift']|None=None
    experience_months:Annotated[int,Field(ge=0,le=600)]|None=None
    roles:list[Literal['developer','reviewer','mentor','lead']]|None=None
    soft_skills:list[Literal['communication','teamwork','planning','feedback']]|None=None
    desired_grade:Literal['Junior','Middle']|None=None
    description:Annotated[str,Field(max_length=3000)]|None=None
