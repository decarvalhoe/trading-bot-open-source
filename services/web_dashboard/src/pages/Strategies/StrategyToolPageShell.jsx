import React from "react";
import PropTypes from "prop-types";

export default function StrategyToolPageShell({ className, title, description, children }) {
  const classes = ["strategy-tool-page", className].filter(Boolean).join(" ");

  return (
    <div className={classes}>
      <header className="page-header">
        <h1 className="heading heading--xl">{title}</h1>
        {description ? <p className="text text--muted">{description}</p> : null}
      </header>
      {children}
    </div>
  );
}

StrategyToolPageShell.propTypes = {
  className: PropTypes.string,
  title: PropTypes.node.isRequired,
  description: PropTypes.node,
  children: PropTypes.node.isRequired,
};

StrategyToolPageShell.defaultProps = {
  className: "",
  description: null,
};
