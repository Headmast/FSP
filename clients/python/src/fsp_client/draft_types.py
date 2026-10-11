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
    preferred_work_formats:list[Literal['remote','office','hybrid']]|None=None
    preferred_employment_types:list[Literal['full_time','part_time','project','internship']]|None=None
    preferred_task_types:list[Literal['development','testing','support','architecture','mentoring']]|None=None
    desired_grade:Literal['Junior','Middle']|None=None
    description:Annotated[str,Field(max_length=3000)]|None=None

class CompanyChanges(Changes):
    name:Annotated[str,Field(max_length=120)]|None=None
    industry:Annotated[str,Field(max_length=120)]|None=None
    description:Annotated[str,Field(max_length=3000)]|None=None

class NeedChanges(Changes):
    title:Annotated[str,Field(max_length=120)]|None=None
    grade:Literal['Junior','Middle']|None=None
    skills:Annotated[str,Field(max_length=200)]|None=None
    tasks:Annotated[str,Field(max_length=1500)]|None=None
    salary_min:Annotated[int,Field(ge=1,le=2147483647)]|None=None
    salary_max:Annotated[int,Field(ge=1,le=2147483647)]|None=None
    work_format:Literal['remote','office','hybrid']|None=None
    employment_type:Literal['','full_time','part_time','project','internship']|None=None
    task_types:list[Literal['development','testing','support','architecture','mentoring']]|None=None
    next_step:Annotated[str,Field(max_length=200)]|None=None

class NewNeed(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:Annotated[str,Field(min_length=1,max_length=120)]
    grade:Literal['Junior','Middle']
    skills:Annotated[str,Field(max_length=200)]=''
    tasks:Annotated[str,Field(min_length=1,max_length=1500)]
    salary_min:Annotated[int,Field(ge=1,le=2147483647)]
    salary_max:Annotated[int,Field(ge=1,le=2147483647)]
    work_format:Literal['remote','office','hybrid']
    employment_type:Literal['','full_time','part_time','project','internship']=''
    task_types:list[Literal['development','testing','support','architecture','mentoring']]=Field(default_factory=list)
    next_step:Annotated[str,Field(max_length=200)]='Знакомство с командой'
