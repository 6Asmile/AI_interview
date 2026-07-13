from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from users.models import User

from .model_gateway import ModelGateway, mask_api_key
from .models import AIModel, AISetting
from .serializers import AISettingSerializer
from .views import AIModelGatewayHealthView


class ModelGatewaySettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='gateway-user',
            email='gateway@example.com',
            password='pass',
        )
        self.chat_model = AIModel.objects.create(
            name='Gateway Chat',
            model_slug='gateway-chat',
            provider='openai_compatible',
            model_type=AIModel.ModelType.CHAT,
            base_url='https://example.com/compatible-mode/v1',
        )
        self.setting = AISetting.objects.create(
            user=self.user,
            chat_model=self.chat_model,
            ai_model=self.chat_model,
            api_keys={str(self.chat_model.id): 'sk-test-secret-value'},
        )

    def test_ai_settings_representation_masks_api_keys(self):
        data = AISettingSerializer(self.setting).data

        self.assertEqual(data['api_keys'][str(self.chat_model.id)], mask_api_key('sk-test-secret-value'))
        self.assertNotIn('sk-test-secret-value', str(data))

    def test_masked_api_key_update_preserves_existing_secret(self):
        masked = mask_api_key('sk-test-secret-value')
        serializer = AISettingSerializer(
            self.setting,
            data={'api_keys': {str(self.chat_model.id): masked}},
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.api_keys[str(self.chat_model.id)], 'sk-test-secret-value')

    def test_blank_api_key_update_removes_secret(self):
        serializer = AISettingSerializer(
            self.setting,
            data={'api_keys': {str(self.chat_model.id): ''}},
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.setting.refresh_from_db()
        self.assertNotIn(str(self.chat_model.id), self.setting.api_keys)

    def test_gateway_health_reports_missing_key_without_fake_success(self):
        self.setting.api_keys = {}
        self.setting.save(update_fields=['api_keys'])
        factory = APIRequestFactory()
        request = factory.post('/settings/ai/health/', {'model_type': AIModel.ModelType.CHAT}, format='json')
        force_authenticate(request, user=self.user)

        response = AIModelGatewayHealthView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['ok'])
        self.assertIn('api_key_missing', response.data['error'])
        self.assertFalse(response.data['config']['has_api_key'])

    def test_gateway_config_snapshot_masks_key(self):
        snapshot = ModelGateway(self.user).config(AIModel.ModelType.CHAT).snapshot()

        self.assertTrue(snapshot['has_api_key'])
        self.assertEqual(snapshot['api_key_masked'], mask_api_key('sk-test-secret-value'))
        self.assertNotIn('sk-test-secret-value', str(snapshot))
