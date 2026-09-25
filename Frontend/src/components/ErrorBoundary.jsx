import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, message: error?.message || "Unexpected application error." };
  }

  componentDidCatch(error, info) {
    console.error("Developer OS UI error", error, info);
  }

  reset = () => {
    this.setState({ hasError: false, message: "" });
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <main className="app-error-boundary" role="alert">
        <div className="app-error-card">
          <span className="eyebrow">Workspace recovery</span>
          <h1>Developer OS needs a quick restart</h1>
          <p>{this.state.message}</p>
          <div className="app-error-actions">
            <button type="button" className="primary-button" onClick={this.reset}>Try again</button>
            <button type="button" className="secondary-button" onClick={() => window.location.reload()}>Reload application</button>
          </div>
        </div>
      </main>
    );
  }
}
