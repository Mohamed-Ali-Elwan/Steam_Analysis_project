import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.tree import DecisionTreeClassifier

from ui import STRETCH_WIDTH


def render_ml_model_trainer(merged_data):
    st.title("ML Model Trainer")
    st.markdown("---")

    st.info("This section trains ML models to predict game tags based on review features.")

    if merged_data is None:
        st.warning(
            "Reviews data not uploaded. Cannot train models. Please upload the reviews dataset."
        )
        return

    st.subheader("Model Configuration")

    col1, col2 = st.columns(2)
    with col1:
        target_col = st.selectbox(
            "Target Variable (Tag to predict)",
            ["primary_tag", "tag"],
            help="Select which column to predict",
        )

    with col2:
        test_size = st.slider("Test Size", 0.1, 0.4, 0.2, 0.05)

    available_features = [
        col
        for col in [
            "recommendation",
            "review_score",
            "total_playtime_hours",
            "total_positive",
            "total_negative",
        ]
        if col in merged_data.columns
    ]

    if not available_features:
        st.warning("No suitable features found for training. Check your data columns.")
        return

    selected_features = st.multiselect(
        "Select Features for Training",
        available_features,
        default=available_features,
        help="Choose which features to use for prediction",
    )

    if not selected_features or target_col not in merged_data.columns:
        st.warning("Please select at least one feature and ensure the target column exists.")
        return

    st.markdown("---")
    st.subheader("Data Preparation")

    valid_mask = merged_data[selected_features + [target_col]].notna().all(axis=1)
    data_filtered = merged_data[valid_mask].copy()

    le = LabelEncoder()
    if data_filtered[target_col].nunique() < 2:
        st.error(
            "Target variable has fewer than 2 unique classes. Cannot train classifier."
        )
        return

    try:
        y = le.fit_transform(data_filtered[target_col])
        X = data_filtered[selected_features]

        st.metric("Training samples", f"{len(X):,}")
        st.metric("Number of classes", f"{len(le.classes_)}")
        st.dataframe(pd.DataFrame({"Class": le.classes_}), **STRETCH_WIDTH)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )

        st.markdown("---")
        st.subheader("Model Training & Results")

        models = {
            "KNN": KNeighborsClassifier(n_neighbors=11, p=2, metric="euclidean"),
            "Gaussian NB": GaussianNB(),
            "Random Forest": RandomForestClassifier(n_estimators=100, random_state=42),
            "Decision Tree": DecisionTreeClassifier(
                criterion="entropy", random_state=42
            ),
        }

        results = []

        for name, model in models.items():
            with st.spinner(f"Training {name}..."):
                model.fit(X_train, y_train)
                y_pred = model.predict(X_test)
                acc = accuracy_score(y_test, y_pred)
                results.append({"Model": name, "Accuracy": acc})

                st.markdown(f"#### {name}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Accuracy", f"{acc:.4f}")

                cm = confusion_matrix(y_test, y_pred)
                fig_cm = px.imshow(
                    cm,
                    labels=dict(x="Predicted", y="Actual", color="Count"),
                    x=le.classes_,
                    y=le.classes_,
                    title=f"{name} - Confusion Matrix",
                )
                fig_cm.update_layout(coloraxis_colorbar=dict(title="Count"))
                st.plotly_chart(fig_cm, **STRETCH_WIDTH)

                if name in ["Random Forest", "Decision Tree"]:
                    importances = model.feature_importances_
                    fig_imp = px.bar(
                        x=selected_features,
                        y=importances,
                        title=f"{name} - Feature Importances",
                        labels={"x": "Feature", "y": "Importance"},
                    )
                    st.plotly_chart(fig_imp, **STRETCH_WIDTH)

                st.markdown("---")

        st.subheader("Model Comparison Summary")
        summary_df = pd.DataFrame(results).sort_values("Accuracy", ascending=False)

        fig_summary = px.bar(
            summary_df,
            x="Model",
            y="Accuracy",
            title="Model Accuracy Comparison",
            color="Accuracy",
            color_continuous_scale="Viridis",
        )
        fig_summary.update_traces(texttemplate="%{y:.4f}", textposition="outside")
        st.plotly_chart(fig_summary, **STRETCH_WIDTH)

        st.dataframe(summary_df.style.format({"Accuracy": "{:.4f}"}), **STRETCH_WIDTH)

    except Exception as e:
        st.error(f"Error during model training: {e}")
