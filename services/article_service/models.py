from pydantic import BaseModel, Field


class ArticleIn(BaseModel):
    sender_id: str = Field(min_length=1, max_length=64)
    recipient_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)


class ArticleAccepted(BaseModel):
    article_id: str
    status: str = "accepted"


class ArticleStatus(BaseModel):
    article_id: str
    stemming_status: str
    wordcloud_status: str
    forwarded: bool
    forwarded_level: str | None