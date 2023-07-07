import pytest
from django import forms
from django.utils import translation
from respa_admin.templatetags.templatetags import form_errors


class MyForm(forms.Form):
    name = forms.CharField(required=True)


MyFormSet = forms.formset_factory(MyForm)


class TestFormErrors:
    error_msg = "Tämä kenttä vaaditaan."

    @pytest.fixture()
    def formset_data(self):
        return {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-MIN_NUM_FORMS": 1,
            "form-MAX_NUM_FORMS": 1,
        }

    def test_form_is_none(self):
        """Any non-form instance should be ignored."""
        assert form_errors(None) == {"errors": []}

    def test_unbound_form(self):
        """If not bound, should not be any errors"""
        assert form_errors(MyForm()) == {"errors": []}

    def test_form_valid(self):
        """If valid, should not be any errors"""
        form = MyForm({"name": "ok"})
        assert form.is_valid()
        assert form_errors(form) == {"errors": []}

    def test_form_invalid(self):
        """If invalid, should be an error"""
        form = MyForm({})
        assert not form.is_valid()

        with translation.override("fi"):
            assert form_errors(form) == {"errors": [self.error_msg]}

    def test_unbound_formset(self):
        """If not bound, should not be any errors"""
        assert form_errors(MyFormSet()) == {"errors": []}

    def test_formset_valid(self, formset_data):
        """If valid, should not be any errors"""
        formset = MyFormSet(
            {
                **formset_data,
                "form-0-name": "ok",
            }
        )
        assert formset.is_valid()
        assert form_errors(formset) == {"errors": []}

    def test_formset_invalid(self, formset_data):
        """If invalid, should be an error"""
        formset = MyFormSet(formset_data)
        assert not formset.is_valid()

        with translation.override("fi"):
            assert form_errors(formset) == {"errors": [self.error_msg]}

    def test_formset_and_form_invalid(self, formset_data):
        """Should render all form errors"""
        form = MyForm({})
        formset = MyFormSet(formset_data)

        assert not form.is_valid()
        assert not formset.is_valid()

        with translation.override("fi"):
            assert form_errors(form, formset) == {
                "errors": [
                    self.error_msg,
                    self.error_msg,
                ]
            }
