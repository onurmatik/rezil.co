# -*- coding: utf-8 -*-

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import Count
from django.dispatch import receiver
from django.template.loader import render_to_string
from premises.models import Contention, Report, Premise
from premises.signals import (reported_as_fallacy, added_premise_for_premise,
                              added_premise_for_contention, supported_a_premise)
from profiles.signals import follow_done


class Profile(AbstractUser):
    following = models.ManyToManyField("self", symmetrical=False)

    @property
    def followers(self):
        # todo: find a way to make reverse relationships
        # with symmetrical false option
        return Profile.objects.filter(following=self)

    @property
    def supported_premise_count(self):
        return self.premise_set.aggregate(Count('supporters'))[
            'supporters__count']


NOTIFICATION_ADDED_PREMISE_FOR_CONTENTION = 0
NOTIFICATION_ADDED_PREMISE_FOR_PREMISE = 1
NOTIFICATION_REPORTED_AS_FALLACY = 2
NOTIFICATION_FOLLOWED_A_PROFILE = 3
NOTIFICATION_SUPPORTED_A_PREMISE = 4

NOTIFICATION_TYPES = (
    (NOTIFICATION_ADDED_PREMISE_FOR_CONTENTION,
     "added-premise-for-contention"),
    (NOTIFICATION_ADDED_PREMISE_FOR_PREMISE,
     "added-premise-for-premise"),
    (NOTIFICATION_REPORTED_AS_FALLACY,
     "reported-as-fallacy"),
    (NOTIFICATION_FOLLOWED_A_PROFILE,
     "followed"),
    (NOTIFICATION_SUPPORTED_A_PREMISE,
     "supported-a-premise"),
)


class Notification(models.Model):
    # sender can be `null` for system notifications
    sender = models.ForeignKey(settings.AUTH_USER_MODEL,
                               null=True, blank=True,
                               related_name="sent_notifications")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL,
                                  related_name="notifications")
    date_created = models.DateTimeField(auto_now_add=True)
    notification_type = models.IntegerField(choices=NOTIFICATION_TYPES)
    is_read = models.BooleanField(default=False)
    target_object_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['is_read', '-date_created']

    def get_target_object(self):
        model = {
            NOTIFICATION_ADDED_PREMISE_FOR_CONTENTION: Premise,
            NOTIFICATION_ADDED_PREMISE_FOR_PREMISE: Premise,
            NOTIFICATION_REPORTED_AS_FALLACY: Report,
            NOTIFICATION_FOLLOWED_A_PROFILE: Profile,
            NOTIFICATION_SUPPORTED_A_PREMISE: Premise,
        }.get(self.notification_type)

        try:
            instance = model.objects.get(pk=self.target_object_id)
        except ObjectDoesNotExist:
            instance = None

        return instance

    def render(self):
        template_name = ("notifications/%s.html" %
                         self.get_notification_type_display())
        return render_to_string(template_name, {
            "notification": self,
            "target_object": self.get_target_object()
        })


@receiver(reported_as_fallacy)
def create_fallacy_notification(sender, report, *args, **kwargs):
    Notification.objects.create(
        sender=None,  # notification should be anonymous
        recipient=report.premise.user,
        notification_type=NOTIFICATION_REPORTED_AS_FALLACY,
        target_object_id=report.id
    )


@receiver(added_premise_for_premise)
def create_premise_answer_notification(sender, premise, *args, **kwargs):
    if premise.user != premise.parent.user:
        Notification.objects.create(
            sender=premise.user,
            recipient=premise.parent.user,
            notification_type=NOTIFICATION_ADDED_PREMISE_FOR_PREMISE,
            target_object_id=premise.id
        )


@receiver(supported_a_premise)
def create_premise_answer_notification(premise, user, *args, **kwargs):
    Notification.objects.create(
        sender=user,
        recipient=premise.user,
        notification_type=NOTIFICATION_SUPPORTED_A_PREMISE,
        target_object_id=premise.id
    )


@receiver(added_premise_for_contention)
def create_contention_contribution_notification(sender, premise, *args, **kwargs):
    if premise.user != premise.argument.user:
        Notification.objects.create(
            sender=premise.user,
            recipient=premise.argument.user,
            notification_type=NOTIFICATION_ADDED_PREMISE_FOR_CONTENTION,
            target_object_id=premise.id
        )


@receiver(follow_done)
def create_following_notification(following, follower, **kwargs):
    """
    Sends notification to the followed user from the follower.
    """
    Notification.objects.create(
        target_object_id=follower.id,
        notification_type=NOTIFICATION_FOLLOWED_A_PROFILE,
        sender=follower,
        recipient_id=following.id
    )
